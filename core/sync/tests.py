import os
import shutil
import tempfile
from unittest.mock import MagicMock, Mock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import resolve

from core.sync.auth import login
from core.sync.client import DEFAULT_SYNC_MAX_FILE_BYTES, fetch_file
from core.sync.orchestrator import _register_entities
from core.sync.registry import registry
from core.sync.syncers import sync_documents, sync_images
from core.uploader.models import Document, Image


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

    @patch("core.sync.auth.requests.post")
    def test_upstream_error_does_not_expose_html_body_or_infrastructure(self, post):
        sensitive_body = (
            "<html>upstream api.internal.example at 10.20.30.40 failed</html>"
        )
        post.return_value = Mock(status_code=502, text=sensitive_body)
        with patch.dict(
            os.environ,
            {
                "API_URL": "https://api.example.test",
                "API_EMAIL": "x@y.test",
                "API_PASSWORD": "secret",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "HTTP 502") as error:
                login()

        message = str(error.exception)
        self.assertNotIn(sensitive_body, message)
        self.assertNotIn("api.internal.example", message)
        self.assertNotIn("10.20.30.40", message)


class SyncFileClientTests(SimpleTestCase):
    api_config = {
        "API_URL": "https://api.example.test",
        "API_EMAIL": "sync@example.test",
        "API_PASSWORD": "secret",
    }

    @patch("core.sync.client.requests.get")
    def test_default_limit_accepts_current_production_image(self, get):
        response = MagicMock()
        response.headers = {"Content-Length": "15645453"}
        response.iter_content.return_value = [b"image-content"]
        get.return_value.__enter__.return_value = response

        with patch.dict(os.environ, self.api_config, clear=True):
            content = fetch_file("/media/images/large.png", "token")

        self.assertEqual(DEFAULT_SYNC_MAX_FILE_BYTES, 25 * 1024 * 1024)
        self.assertEqual(content, b"image-content")

    @patch("core.sync.client.requests.get")
    def test_rejects_content_length_above_configured_limit(self, get):
        response = MagicMock()
        response.headers = {"Content-Length": "5"}
        get.return_value.__enter__.return_value = response

        with patch.dict(
            os.environ,
            {**self.api_config, "SYNC_MAX_FILE_BYTES": "4"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "excede o limite de 4 bytes"):
                fetch_file("/media/images/large.png", "token")

    @patch("core.sync.client.requests.get")
    def test_rejects_streamed_chunks_above_configured_limit(self, get):
        response = MagicMock()
        response.headers = {}
        response.iter_content.return_value = [b"123", b"45"]
        get.return_value.__enter__.return_value = response

        with patch.dict(
            os.environ,
            {**self.api_config, "SYNC_MAX_FILE_BYTES": "4"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "excede o limite de 4 bytes"):
                fetch_file("/media/images/large.png", "token")

    @patch("core.sync.client.requests.get")
    def test_rejects_invalid_config_before_downloading(self, get):
        with patch.dict(
            os.environ,
            {**self.api_config, "SYNC_MAX_FILE_BYTES": "not-an-integer"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "deve ser um número inteiro"):
                fetch_file("/media/images/large.png", "token")

        get.assert_not_called()


class SyncEndpointTests(SimpleTestCase):
    def test_weather_endpoint_matches_router_without_trailing_slash(self):
        _register_entities()

        self.assertEqual(registry.get("weather").endpoint, "/api/weather/weather")
        self.assertEqual(resolve("/api/weather/weather").url_name, "weather-list")


class SyncMediaTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_root)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)

    @patch("core.sync.syncers.fetch_file", return_value=b"image-content")
    def test_imports_image_and_preserves_attachment_key_and_suffix(self, fetch_file):
        data = [
            {
                "attachment_key": "73f1a3d0-0f15-4c4d-ae2f-703e665808f7",
                "url": "/media/images/remote-image.png",
                "description": "Imagem remota",
            }
        ]

        self.assertEqual(sync_images(data, "token"), (1, 0))
        image = Image.objects.get()
        self.assertEqual(str(image.attachment_key), data[0]["attachment_key"])
        self.assertTrue(image.file.name.endswith(".png"))
        self.assertEqual(sync_images(data, "token"), (0, 0))
        fetch_file.assert_called_once_with(data[0]["url"], "token")

    @patch("core.sync.syncers.fetch_file", return_value=b"pdf-content")
    def test_imports_document_idempotently_and_preserves_suffix(self, fetch_file):
        data = [
            {
                "attachment_key": "4f696444-92c8-4dea-8ae5-5a59026f272f",
                "url": "/media/documents/remote-document.PDF",
                "description": "Documento remoto",
            }
        ]

        self.assertEqual(sync_documents(data, "token"), (1, 0))
        document = Document.objects.get()
        self.assertEqual(str(document.attachment_key), data[0]["attachment_key"])
        self.assertTrue(document.file.name.endswith(".pdf"))
        self.assertEqual(sync_documents(data, "token"), (0, 0))
        fetch_file.assert_called_once_with(data[0]["url"], "token")

    @patch("core.sync.syncers.fetch_file", return_value=b"pdf-content")
    def test_repairs_existing_document_without_file(self, fetch_file):
        document = Document.objects.create(
            attachment_key="e811c36d-4937-4834-8f1f-6e88339bac05",
            description="Antiga",
        )
        data = [
            {
                "attachment_key": str(document.attachment_key),
                "url": "/media/documents/repaired.pdf",
                "description": "Reparada",
            }
        ]

        self.assertEqual(sync_documents(data, "token"), (0, 1))
        document.refresh_from_db()
        self.assertTrue(document.file.name.endswith(".pdf"))
        self.assertEqual(document.description, "Reparada")
        fetch_file.assert_called_once_with(data[0]["url"], "token")
