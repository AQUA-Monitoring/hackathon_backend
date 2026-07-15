"""Lightweight demo control views used even without the ML service."""

from __future__ import annotations

from typing import Any

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.flood_camera_monitoring.infra.demo_stream_client import (
    DemoStreamClient,
    DemoStreamUnavailable,
)
from core.flood_camera_monitoring.presentation.serializers import DemoStateSerializer
from core.users.permissions import IsAppAdmin


def _client() -> DemoStreamClient:
    return DemoStreamClient()


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = dict(payload)
    segment = output.get("segment")
    if isinstance(segment, dict):
        output["segment"] = {
            key: value for key, value in segment.items() if key != "internal_url"
        }
    return output


class DemoStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        try:
            payload = _client().get_state()
        except DemoStreamUnavailable as exc:
            return Response(
                {
                    "enabled": False,
                    "status": "unavailable",
                    "detail": str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"enabled": True, **_public_payload(payload)})


class DemoStateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAppAdmin]

    def post(self, request, *args, **kwargs):
        serializer = DemoStateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        requested_state = serializer.validated_data["state"]
        client = _client()
        try:
            previous = client.get_state()
            available_states = previous.get("available_states", [])
            if requested_state not in available_states:
                return Response(
                    {
                        "detail": f"State '{requested_state}' is not available in this scenario",
                        "available_states": available_states,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payload = client.set_state(requested_state)
        except DemoStreamUnavailable as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        return Response({"enabled": True, **_public_payload(payload)})
