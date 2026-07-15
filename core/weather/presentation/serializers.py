from rest_framework import serializers
from core.weather.models import Weather

class WeatherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Weather
        fields = '__all__'