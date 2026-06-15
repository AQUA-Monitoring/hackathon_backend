from rest_framework import viewsets

from core.weather.models.weather import Weather
from core.weather.presentation.serializers import WeatherSerializer

class WeatherViewSet(viewsets.ModelViewSet):
    queryset = Weather.objects.all()
    serializer_class = WeatherSerializer

    def perform_create(self, serializer):
        instance = serializer.save()
        