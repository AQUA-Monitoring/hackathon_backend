from rest_framework.permissions import BasePermission

from core.users.infra.models import User


class IsAppAdmin(BasePermission):
    """Allow only authenticated users whose application type is ADMIN."""

    message = "Apenas administradores podem alterar a transmissão demo."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        return bool(
            user
            and getattr(user, "is_authenticated", False)
            and (
                getattr(user, "type", None) == User.UserType.ADMIN
                or getattr(user, "is_staff", False)
            )
        )
