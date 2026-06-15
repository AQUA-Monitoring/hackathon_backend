import requests

class WeatherService():
    def fill_climate(lat, lon, start, end):
        url = 'https://archive-api.open-meteo.com/v1/archive'
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": ",".join([
                "precipitation_sum",
                "temperature_2m_mean",
                "relative_humidity_2m_mean",
                "surface_pressure_mean"
            ]),
            "timezone": "America/Sao_Paulo"
        }

        response = requests.get(url, params)
        data = response.json()
        return data