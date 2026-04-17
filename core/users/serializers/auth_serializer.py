from __future__ import annotations
from rest_framework import serializers

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
