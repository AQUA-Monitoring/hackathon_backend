from rest_framework.permissions import BasePermission

from core.users.serializers.auth import SYNC_AUTH_MODEL, SYNC_SCOPE


class IsSyncSuperuser(BasePermission):
    message = "Token de sincronização inválido."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        token = getattr(request, "auth", None)
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and getattr(user, "is_active", False)
            and getattr(user, "is_superuser", False)
            and token
            and token.get("scope") == SYNC_SCOPE
            and token.get("auth_model") == SYNC_AUTH_MODEL
        )
