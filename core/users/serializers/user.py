from rest_framework import serializers


class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    profile_picture = serializers.URLField(required=False, allow_blank=True)


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)
    profile_picture = serializers.FileField(required=False, allow_null=True)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
