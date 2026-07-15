from core.weather.utils import current_weather, future_weather

def process_weather(self, lat, lon, start, end):
    current = current_weather(lat, lon)
    future = future_weather(lat, lon)

    past_hours = current["hourly"]["time"]
    future_hours = future_hours["hourly"]["time"]