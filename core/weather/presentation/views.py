from rest_framework import viewsets
from core.weather.models import Weather
from core.weather.presentation.serializers import WeatherSerializer

class WeatherViewSet(viewsets.ModelViewSet):
    queryset = Weather.objects.all()
    serializer_class = WeatherSerializer