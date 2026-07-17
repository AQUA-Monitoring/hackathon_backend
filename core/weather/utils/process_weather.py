from core.weather.utils import current_weather, future_weather

def process_weather(self, lat, lon, start, end):
    weather = []
    current = current_weather(lat, lon)
    weather.append(current)
    future = future_weather(lat, lon)
    weather.append(future)
    return weather