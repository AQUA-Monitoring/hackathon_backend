from django.db import models
from core.occurrences.models import Occurrence

class Weather(models.Model):
    date = models.DateField()
    latitude = models.FloatField()
    longitude = models.FloatField()
    neighborhood = models.CharField()
    rain = models.FloatField(null=True)
    temperature = models.FloatField(null=True)
    humidity = models.FloatField(null=True)
    elevation = models.FloatField(null=True)
    pressure = models.FloatField(null=True)
    river_discharge = models.FloatField(null=True)
    occurrence = models.ForeignKey(Occurrence, on_delete=models.PROTECT, related_name="occurrence", null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["date", "latitude", "longitude", "neighborhood"],
                name="unique_weather_per_day_location"
            )
        ]

    def __str__(self):
        return f'{self.date} - {self.neighborhood}'