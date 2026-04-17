from __future__ import annotations
from rest_framework_simplejwt.authentication import JWTAuthentication as SimpleJWTAuth
from django.utils.translation import gettext_lazy as _


class AppJWTAuthentication(SimpleJWTAuth):
    def get_user(self, validated_token):  # type: ignore[override]
        # Import locally to avoid circular import during DRF settings initialization
        from rest_framework.exceptions import AuthenticationFailed
        from core.users.infra.models import User

        user_id = validated_token.get("user_id")
        if not user_id:
            raise AuthenticationFailed(_("Invalid token: no user_id"))
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed(_("User not found"))
