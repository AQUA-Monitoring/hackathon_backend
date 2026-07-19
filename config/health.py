import redis
from django.conf import settings
from django.db import connections
from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Report whether the dependencies required to serve requests are available."""
    checks = {"database": False, "redis": False}

    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone() == (1,)
    except Exception:
        pass

    try:
        client = redis.from_url(
            settings.REDIS_CACHE_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        checks["redis"] = bool(client.ping())
    except Exception:
        pass

    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=200 if healthy else 503,
    )
