from django.db import models


class TimestampedModel(models.Model):
    """Base abstrata para registros com auditoria temporal básica."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
