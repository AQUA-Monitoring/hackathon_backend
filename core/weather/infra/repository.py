from core.weather.domain.repository import WeatherRepository
from core.weather.infra.models import Weather
from core.weather.infra.services.weather import fillClimate as fillClimateService, fillElevation, fillFutureClimate, fillFlood
from datetime import date, timedelta

today = date.today().isoformat()
forecast_start = (date.today() - timedelta(days=3)).isoformat()
forecast_end = (date.today() + timedelta(days=7)).isoformat()

class WeatherRepositoryImpl(WeatherRepository):
    def fillAll(self, lat, lon, neighborhood, start, end):
        weather = self.fillWeather(lat, lon, start, min(end, today))
        future = self.fillFutureWeather(lat, lon)
        flood = self.fillFlood(lat, lon)
        elevation = self.fillElevation(lat, lon)
        climates = []

        for i in range(len(weather["days"])):
            climates.append(
                Weather(
                    date=weather["days"][i],
                    neighborhood=neighborhood,
                    latitude=lat,
                    longitude=lon,
                    rain=weather.get("rain", [None] * len(weather["days"]))[i],
                    temperature=weather.get("temperature", [None] * len(weather["days"]))[i],
                    humidity=weather.get("humidity", [None] * len(weather["days"]))[i],
                    elevation=elevation.get("elevation"),
                    pressure=weather.get("pressure", [None] * len(weather["days"]))[i],
                    river_discharge=flood.get("river_discharge", [None])[i] if i < len(flood.get("river_discharge", [])) else None,
                )
            )

        future_daily = {}
        for i in range(len(future["days"])):
            d = future["days"][i]
            if d not in future_daily:
                future_daily[d] = {"rain": [], "temperature": [], "humidity": []}
            future_daily[d]["rain"].append(future.get("rain", [])[i] if i < len(future.get("rain", [])) else None)
            future_daily[d]["temperature"].append(future.get("temperature", [])[i] if i < len(future.get("temperature", [])) else None)
            future_daily[d]["humidity"].append(future.get("humidity", [])[i] if i < len(future.get("humidity", [])) else None)

        for j, (d, vals) in enumerate(future_daily.items()):
            rain_vals = [v for v in vals["rain"] if v is not None]
            temp_vals = [v for v in vals["temperature"] if v is not None]
            hum_vals = [v for v in vals["humidity"] if v is not None]
            climates.append(
                Weather(
                    date=d,
                    neighborhood=neighborhood,
                    latitude=lat,
                    longitude=lon,
                    rain=sum(rain_vals) if rain_vals else None,
                    temperature=sum(temp_vals) / len(temp_vals) if temp_vals else None,
                    humidity=sum(hum_vals) / len(hum_vals) if hum_vals else None,
                    elevation=elevation.get("elevation"),
                    pressure=None,
                    river_discharge=flood.get("river_discharge", [None])[j] if j < len(flood.get("river_discharge", [])) else None,
                )
            )

        Weather.objects.bulk_create(climates, ignore_conflicts=True)

        return {
            "days": weather["days"] + list(future_daily.keys()),
            "rain": weather.get("rain", []),
            "temp": weather.get("temperature", []),
            "humidity": weather.get("humidity", []),
            "pressure": weather.get("pressure", []),
            "elevation": elevation["elevation"],
        }

    def fillWeather(self, lat, lon, start, end):
        return fillClimateService(lat, lon, start, end)
    
    def fillFutureWeather(self, lat, lon):
        return fillFutureClimate(lat, lon, forecast_start, forecast_end)
    
    def fillFlood(self, lat, lon):
        return fillFlood(lat, lon)

    def fillElevation(self, lat, lon):
        return fillElevation(lat, lon)