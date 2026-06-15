from celery import shared_task
from core.weather.utils import fill_climate, fill_elevation, fill_future

@shared_task
def fill_weather(lat, lon, start, end):
    fill_climate()
    fill_elevation()
    fill_future()