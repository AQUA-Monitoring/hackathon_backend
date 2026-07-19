from __future__ import annotations
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from core.users.service import UsersService


class EmailTokenObtainPairSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=6)

    def validate(self, attrs):
        email = attrs.get("email", "")
        password = attrs.get("password", "")
        service = UsersService()
        user = service.authenticate(email=email, password=password)

        tokens = service.generate_tokens_for_user(user)
        return {"access": tokens["access"], "refresh": tokens["refresh"]}


class AppTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh tokens issued for Aqua's UUID-backed application user."""

    def validate(self, attrs):
        from core.users.infra.models import User

        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        if not user_id or not User.objects.filter(pk=user_id).exists():
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        data = {"access": str(refresh.access_token)}
        if api_settings.ROTATE_REFRESH_TOKENS:
            if api_settings.BLACKLIST_AFTER_ROTATION:
                try:
                    refresh.blacklist()
                except AttributeError:
                    pass
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            refresh.outstand()
            data["refresh"] = str(refresh)
        return data
