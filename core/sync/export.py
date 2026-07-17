import json

from django.apps import apps
from django.core import serializers
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


EXPORT_MODELS = [
    "addressing.City",
    "addressing.Region",
    "addressing.Neighborhood",
    "addressing.Address",
    "uploader.Image",
    "uploader.Document",
    "uploader.Video",
    "users.User",
    "flood_camera_monitoring.Camera",
    "flood_camera_monitoring.FloodDetectionRecord",
    "occurrences.Occurrence",
    "blog.Post",
    "weather.Weather",
    "forecast.Forecast",
    "flood_point_registering.Flood_Point_Register",
]


class ExportView(APIView):
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get(self, request):
        full_data = []
        for label in EXPORT_MODELS:
            try:
                app_label, model_name = label.split(".")
                model_class = apps.get_model(app_label, model_name)
                if model_class is None:
                    continue
                queryset = model_class.objects.all().order_by("pk")[:10000]
                chunk = serializers.serialize("json", queryset, indent=2)
                chunk_data = json.loads(chunk)
                full_data.extend(chunk_data)
            except LookupError:
                continue

        return Response(full_data, status=status.HTTP_200_OK)
