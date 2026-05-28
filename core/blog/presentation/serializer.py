from rest_framework import serializers
from core.uploader.serializers import ImageSerializer
from core.blog.infra.models import Post  

class PostSerializer(serializers.ModelSerializer):
    banner_image = ImageSerializer(required=True)
    content_image = ImageSerializer(required=False)

    class Meta:
        model = Post
        fields = '__all__'