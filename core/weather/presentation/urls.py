from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.weather.presentation.views import WeatherViewSet

router = DefaultRouter()
router.register()

urlpatterns = [
    path("", include(router.urls)),
]
