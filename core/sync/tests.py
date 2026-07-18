import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from core.sync.auth import login


class SyncAuthClientTests(SimpleTestCase):
    @patch("core.sync.auth.requests.post")
    def test_login_uses_dedicated_sync_token_route(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {"access": "sync-access-token"}
        post.return_value = response

        with patch.dict(
            os.environ,
            {
                "API_URL": "https://api.example.test/",
                "API_EMAIL": "sync@example.test",
                "API_PASSWORD": "secret",
            },
        ):
            self.assertEqual(login(), "sync-access-token")

        post.assert_called_once_with(
            "https://api.example.test/api/sync/token/",
            json={"email": "sync@example.test", "password": "secret"},
            timeout=30,
        )

    @patch("core.sync.auth.requests.post")
    def test_authentication_error_does_not_repeat_remote_body(self, post):
        post.return_value = Mock(status_code=401, text="sensitive remote body")
        with patch.dict(
            os.environ,
            {
                "API_URL": "https://api.example.test",
                "API_EMAIL": "x@y.test",
                "API_PASSWORD": "secret",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "credenciais inválidas") as error:
                login()
        self.assertNotIn("sensitive remote body", str(error.exception))
