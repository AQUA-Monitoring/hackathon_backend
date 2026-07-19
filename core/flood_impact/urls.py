from django.urls import include, path
from rest_framework.routers import DefaultRouter

from core.flood_impact.views import FloodImpactEventViewSet, RoadImpactHotspotViewSet

router = DefaultRouter()
router.register("events", FloodImpactEventViewSet, basename="flood-impact-events")
router.register("hotspots", RoadImpactHotspotViewSet, basename="flood-impact-hotspots")

urlpatterns = [path("", include(router.urls))]
