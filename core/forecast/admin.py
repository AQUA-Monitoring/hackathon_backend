from django.contrib import admin
from core.forecast.models import Forecast

@admin.register(Forecast)
class ForecastAdmin(admin.ModelAdmin):
    list_display = ("date", "latitude", "longitude", "probability")
    list_filter = ("date",)
    search_fields = ("latitude", "longitude")