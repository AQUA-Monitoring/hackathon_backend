from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import SAFE_METHODS, AllowAny

from core.users.permissions import IsAppAdmin
from core.flood_point_registering.infra.models import Flood_Point_Register
from core.flood_point_registering.presentation.serializers.RegisterSerializer import (
    FloodPointRegisterSerializer,
)


class FloodPointRegister(ModelViewSet):
    queryset = Flood_Point_Register.objects.select_related("spatial_event__current_revision")
    serializer_class = FloodPointRegisterSerializer

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [AllowAny()]
        return [IsAppAdmin()]

    def get_queryset(self):
        qs = Flood_Point_Register.objects.select_related("spatial_event__current_revision")
        # Only return ACTIVE points by default in list and custom active action
        if getattr(self, "action", None) in {"list", "active"}:
            return qs.active().order_by("-created_at")
        return qs

    @action(detail=False, methods=["get"], url_path="active")
    def active(self, request):
        # Active = created_at <= now <= finished_at
        qs = self.get_queryset().order_by("-created_at")
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
