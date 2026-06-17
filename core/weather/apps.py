from django.apps import AppConfig


class WeatherConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.weather'

    def ready(self):
        import core.weather.presentation.tasks  # noqa: F401
