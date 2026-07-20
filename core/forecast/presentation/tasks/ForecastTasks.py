from celery import shared_task
from core.forecast.services import ForecastRepoImpl, floodingPredict

@shared_task
def forecast():
    repo = ForecastRepoImpl()
    floodingPredict(repo)
