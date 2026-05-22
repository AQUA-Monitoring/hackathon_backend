from django.db import models
from uploader.models.image import Image

import uuid

class Post(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=50)  # categoria (ex: Causas)
    author = models.CharField(max_length=100, null=True, blank=True)
    content = models.TextField(null=True, blank=True)
    banner_image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
    content_image = models.ForeignKey(Image, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title