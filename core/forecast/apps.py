from django.apps import AppConfig


class ForecastConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core.forecast'

    def ready(self):
        import core.forecast.presentation.tasks  # noqa: F401
