from rest_framework.viewsets import ModelViewSet
from core.forecast.models import Forecast
from core.forecast.presentation.serializers.forecast import ForecastSerializer

class ForecastViewSet(ModelViewSet):
    queryset = Forecast.objects.all()
    serializer_class = ForecastSerializer