from rest_framework import views, status
from rest_framework.response import Response
from core.weather.presentation.serializers import WeatherSerializer
from core.weather.services.weather import WeatherService

class WeatherAPIView(views.APIView):
    def post(self, request, *args, **kwargs):
        serializer = WeatherSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        weather = WeatherService.fill_climate(serializer.validated_data)
        return Response(weather, status=status.HTTP_200_OK)