from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from core.users.infra.models import User as AppUser
from core.users.serializers.auth import AppJWTAuthentication


class SyncTokenTests(APITestCase):
    password = "senha-segura-123"

    def setUp(self):
        self.client = APIClient()
        self.superuser = get_user_model().objects.create_superuser(
            username="sync-admin",
            email="sync-admin@example.com",
            password=self.password,
        )

    def issue_sync_token(self) -> str:
        response = self.client.post(
            "/api/sync/token/",
            {"email": self.superuser.email, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.data), {"access", "token_type", "expires_in"}
        )
        self.assertEqual(response.data["token_type"], "Bearer")
        self.assertEqual(response.data["expires_in"], 3600)
        return response.data["access"]

    def test_active_superuser_receives_sync_token(self):
        token = AccessToken(self.issue_sync_token())
        self.assertEqual(token["scope"], "sync:read")
        self.assertEqual(token["auth_model"], "django")
        self.assertEqual(token["user_id"], self.superuser.pk)
        self.assertEqual(token["exp"] - token["iat"], 3600)

    def test_invalid_sync_credentials_are_denied_generically(self):
        common = get_user_model().objects.create_user(
            username="common", email="common@example.com", password=self.password
        )
        inactive = get_user_model().objects.create_superuser(
            username="inactive", email="inactive@example.com",
            password=self.password, is_active=False,
        )
        app_admin = AppUser(name="App admin", email="app-admin@example.com", type="admin")
        app_admin.set_password(self.password)
        app_admin.save()

        for email, password in (
            (common.email, self.password),
            (inactive.email, self.password),
            (self.superuser.email, "senha-incorreta"),
            (app_admin.email, self.password),
        ):
            with self.subTest(email=email):
                response = self.client.post(
                    "/api/sync/token/", {"email": email, "password": password},
                    format="json",
                )
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.data["detail"], "Credenciais inválidas")

    def test_flags_are_rechecked_and_partial_sync_claims_are_denied(self):
        authentication = AppJWTAuthentication()
        token = AccessToken(self.issue_sync_token())

        partial = AccessToken()
        partial["user_id"] = self.superuser.pk
        partial["scope"] = "sync:read"
        with self.assertRaises(AuthenticationFailed):
            authentication.get_user(partial)

        self.superuser.is_active = False
        self.superuser.save(update_fields=["is_active"])
        with self.assertRaises(AuthenticationFailed):
            authentication.get_user(token)

        self.superuser.is_active = True
        self.superuser.is_superuser = False
        self.superuser.save(update_fields=["is_active", "is_superuser"])
        with self.assertRaises(AuthenticationFailed):
            authentication.get_user(token)

    def test_normal_login_remains_compatible_and_does_not_become_sync(self):
        app_user = AppUser(name="Normal", email="normal@example.com")
        app_user.set_password(self.password)
        app_user.save()
        response = self.client.post(
            "/api/auth/token/",
            {"email": app_user.email, "password": self.password}, format="json",
        )
        self.assertEqual(response.status_code, 200)
        token = AccessToken(response.data["access"])
        self.assertNotIn("scope", token)
        self.assertNotIn("auth_model", token)
        self.assertEqual(AppJWTAuthentication().get_user(token), app_user)

    def test_export_accepts_sync_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.issue_sync_token()}")
        self.assertEqual(self.client.get("/api/export/").status_code, 200)
