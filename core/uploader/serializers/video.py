from django.conf import settings
from rest_framework import serializers

from core.uploader.helpers.files import VIDEO_CONTENT_TYPES, get_content_type
from core.uploader.models import Video


class VideoUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ["attachment_key", "file", "description", "uploaded_on", "url"]
        read_only_fields = ["attachment_key", "uploaded_on", "url"]
        extra_kwargs = {"file": {"write_only": True}}

    def validate_file(self, value):
        max_bytes = settings.UPLOADER_VIDEO_MAX_BYTES
        if value.size > max_bytes:
            raise serializers.ValidationError(
                f"Video exceeds the limit of {max_bytes} bytes."
            )
        if get_content_type(value) not in VIDEO_CONTENT_TYPES:
            raise serializers.ValidationError("Invalid or unsupported video.")
        return value


class VideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Video
        fields = ["attachment_key", "url", "description", "uploaded_on"]
        read_only_fields = ["attachment_key", "url", "uploaded_on"]

    def create(self, validated_data):
        raise NotImplementedError("Use VideoUploadSerializer to create videos.")
