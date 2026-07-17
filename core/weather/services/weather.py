from core.weather.models import Weather
from core.weather.utils.all_coordinates import all_coordinates

class WeatherService:
    def fill_climate(instance: Weather):
        weather = all_coordinates()
        instance.objects.update_or_create(weather)