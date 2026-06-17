from core.forecast.domain.repository import MachineLearningRepository
from core.weather.infra.models import Weather
from core.forecast.infra.models import Forecast

class ForecastRepoImpl(MachineLearningRepository):
    def getCoords(self):
        return Weather.objects.values("latitude", "longitude").distinct()
    
    def getWeatherByCoord(self, lat, lon):
        return Weather.objects.filter(latitude=lat, longitude=lon)
    
    def forecast(self, lat, lon, date, flood, probability):
        Forecast.objects.update_or_create(
            latitude=lat,
            longitude=lon,
            date=date,
            defaults={"flood": flood, "probability": probability}
        )