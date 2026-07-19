from django.contrib import admin

from core.uploader.models import Document, Image, Video

admin.site.register(Image)
admin.site.register(Document)
admin.site.register(Video)
