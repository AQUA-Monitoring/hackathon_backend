from rest_framework import serializers


class UserSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    profile_picture = serializers.SerializerMethodField()

    @staticmethod
    def get_profile_picture(user):
        if user.profile_picture:
            return user.profile_picture.url
        return user.profile_picture_url or None


class SignupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=6, max_length=128, write_only=True)
    profile_picture = serializers.FileField(required=False, allow_null=True)
    profile_picture_id = serializers.UUIDField(required=False, allow_null=True)


class UpdateUserSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100, required=False)
    email = serializers.EmailField(required=False)
    profile_picture = serializers.FileField(required=False, allow_null=True)
    profile_picture_id = serializers.UUIDField(required=False, allow_null=True)


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
