from rest_framework import serializers
from core.forecast.models import Forecast

class ForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = Forecast
        fields = "__all__"