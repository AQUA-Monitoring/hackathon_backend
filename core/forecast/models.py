from django.db import models

class Forecast(models.Model):
    latitude = models.FloatField()
    longitude = models.FloatField()
    date = models.DateField()
    flood = models.FloatField()
    probability = models.FloatField()

    class Meta:
        unique_together = ("latitude", "longitude", "date")
        verbose_name_plural = "Forecasts"