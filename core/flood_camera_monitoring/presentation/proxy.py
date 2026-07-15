"""Gateway proxy for flood routes unavailable in the lightweight API image."""

from __future__ import annotations

import requests
from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt


HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _error_response(detail: str, code: str, status: int) -> JsonResponse:
    return JsonResponse({"detail": detail, "code": code}, status=status)


def _forward_headers(request: HttpRequest) -> dict[str, str]:
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS | {"host", "content-length"}
    }
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    remote_addr = request.META.get("REMOTE_ADDR")
    if remote_addr:
        headers["X-Forwarded-For"] = (
            f"{forwarded_for}, {remote_addr}" if forwarded_for else remote_addr
        )
    headers["X-Forwarded-Proto"] = request.scheme
    return headers


@csrf_exempt
def proxy_flood_camera(request: HttpRequest, path: str = "") -> HttpResponse:
    target = f"{settings.FLOOD_CAMERA_SERVICE_URL}/api/flood_monitoring/"
    if path:
        target += path
    query_string = request.META.get("QUERY_STRING", "")
    if query_string:
        target = f"{target}?{query_string}"

    try:
        upstream = requests.request(
            method=request.method,
            url=target,
            headers=_forward_headers(request),
            data=request.body or None,
            timeout=(
                settings.FLOOD_CAMERA_PROXY_CONNECT_TIMEOUT_SECONDS,
                settings.FLOOD_CAMERA_PROXY_READ_TIMEOUT_SECONDS,
            ),
            allow_redirects=False,
        )
    except requests.Timeout:
        return _error_response(
            "Flood camera monitoring timed out", "flood_camera_timeout", 504
        )
    except requests.RequestException:
        return _error_response(
            "Flood camera monitoring is unavailable",
            "flood_camera_unavailable",
            503,
        )

    response = HttpResponse(content=upstream.content, status=upstream.status_code)
    for name, value in upstream.headers.items():
        if name.lower() not in HOP_BY_HOP_HEADERS | {"content-length"}:
            response[name] = value
    return response
