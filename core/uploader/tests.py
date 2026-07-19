from django.test import SimpleTestCase

from core.uploader.models import Document, Image
from core.uploader.models.document import document_file_path
from core.uploader.models.image import image_file_path
from core.uploader.serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    ImageSerializer,
)


class MediaContractTests(SimpleTestCase):
    def test_storage_paths_use_filename_suffix_with_empty_file_fields(self):
        image = Image()
        document = Document()

        self.assertFalse(image.file)
        self.assertFalse(document.file)
        self.assertTrue(image_file_path(image, "PHOTO.PNG").endswith(".png"))
        self.assertTrue(document_file_path(document, "REPORT.PDF").endswith(".pdf"))

    def test_serializers_return_null_url_when_file_is_empty(self):
        self.assertIsNone(ImageSerializer(Image()).data["url"])
        self.assertIsNone(DocumentSerializer(Document()).data["url"])

    def test_document_upload_serializer_exposes_read_only_url(self):
        serializer = DocumentUploadSerializer(Document())

        self.assertIn("url", serializer.data)
        self.assertIsNone(serializer.data["url"])
