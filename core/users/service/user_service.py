from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rest_framework import exceptions
from rest_framework_simplejwt.tokens import RefreshToken

from core.users.infra.models import User
from core.uploader.application.services import UploadBinaryService
from core.uploader.infra.django_storage_uploader import DjangoStorageUploader


@dataclass
class UsersService:
    """Application service for user auth/account flows."""

    upload_base_dir: str = "uploads"

    @staticmethod
    def normalize_email(email: str) -> str:
        return str(email).lower().strip()

    def generate_tokens_for_user(self, user: User) -> dict[str, str]:
        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    def create_user(
        self,
        *,
        name: str,
        email: str,
        password: str,
        profile_picture: Any | None = None,
    ) -> User:
        normalized_email = self.normalize_email(email)
        if User.objects.filter(email=normalized_email).exists():
            raise ValueError("duplicate_email")

        user = User(name=name, email=normalized_email)
        user.set_password(password)

        if profile_picture:
            data = profile_picture.read()
            path = f"users/{normalized_email}/profile/{profile_picture.name}"
            uploader = DjangoStorageUploader(base_dir=self.upload_base_dir)
            result = UploadBinaryService(uploader).execute(
                data=data,
                path=path,
                content_type=getattr(profile_picture, "content_type", None),
            )
            user.profile_picture = result.url

        user.save()
        return user

    def authenticate(self, *, email: str, password: str) -> User:
        normalized_email = self.normalize_email(email)
        try:
            user = User.objects.get(email=normalized_email)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("Credenciais inválidas") from exc

        if not user.check_password(password):
            raise exceptions.AuthenticationFailed("Credenciais inválidas")

        return user

    @staticmethod
    def me_payload(user: User) -> dict[str, str]:
        return {
            "id": str(user.id),
            "name": user.name,
            "type": user.type,
            "email": user.email,
            "profile_picture": user.profile_picture,
        }
