"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenRefreshView,
)
from core.users.presentation.auth_views import EmailTokenObtainPairView

router = DefaultRouter()

urlpatterns = [
    path("admin/", admin.site.urls),
    # JWT auth endpoints
    # Single auth token route using email/password
    path(
        "api/auth/token/", EmailTokenObtainPairView.as_view(), name="token_obtain_pair"
    ),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/users/", include("core.users.presentation.urls")),
    path("api/weather/", include("core.weather.presentation.urls")),
    path("api/forecast/", include("core.forecast.presentation.urls")),
    path("api/occurrences/", include("core.occurrences.presentation.urls")),
    path(
        "api/flood_monitoring/",
        include("core.flood_camera_monitoring.presentation.urls"),
    ),
    path("api/upload/", include("core.uploader.presentation.urls")),
    path("api/addressing/", include("core.addressing.presentation.urls")),
    path("api/donate/", include("core.donation.presentation.urls")),
    path(
        "api/floods_point/", include("core.flood_point_registering.presentation.urls")
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
