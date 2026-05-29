from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.users.serializers.user import (
    UserSerializer,
    SignupSerializer,
    UpdateUserSerializer,
)
from core.users.service import UsersService


class UsersViewSet(viewsets.ViewSet):
    """Auth-related endpoints grouped under a router.

    Routes:
      - POST /users/signup
      - GET  /users/me
    """

    permission_classes = [permissions.AllowAny]

    @staticmethod
    def _users_service() -> UsersService:
        return UsersService()

    @action(
        detail=False,
        methods=["post"],
        url_path="signup",
        permission_classes=[permissions.AllowAny],
    )
    def signup(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = self._users_service()

        try:
            user = service.create_user(
                name=serializer.validated_data["name"],
                email=serializer.validated_data["email"],
                password=serializer.validated_data["password"],
                profile_picture=serializer.validated_data.get("profile_picture"),
                profile_picture_id=serializer.validated_data.get("profile_picture_id"),
            )
        except ValueError as exc:
            if str(exc) == "duplicate_email":
                return Response(
                    {"detail": "E-mail já cadastrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if str(exc) == "invalid_profile_picture":
                return Response(
                    {"detail": "Imagem de perfil inválida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        tokens = service.generate_tokens_for_user(user)
        return Response(
            {"user": UserSerializer(user).data, "tokens": tokens},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get", "patch", "put"],
        url_path="me",
        permission_classes=[permissions.IsAuthenticated],
    )
    def me(self, request):
        service = self._users_service()

        if request.method == "GET":
            return Response(service.me_payload(request.user), status=status.HTTP_200_OK)

        serializer = UpdateUserSerializer(
            data=request.data,
            partial=request.method == "PATCH",
        )
        serializer.is_valid(raise_exception=True)

        try:
            user = service.update_user(
                user=request.user,
                name=serializer.validated_data.get("name"),
                email=serializer.validated_data.get("email"),
                profile_picture=serializer.validated_data.get("profile_picture"),
                profile_picture_id=serializer.validated_data.get("profile_picture_id"),
            )
        except ValueError as exc:
            if str(exc) == "invalid_profile_picture":
                return Response(
                    {"detail": "Imagem de perfil inválida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if str(exc) == "duplicate_email":
                return Response(
                    {"detail": "E-mail já cadastrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            raise

        return Response(UserSerializer(user).data, status=status.HTTP_200_OK)
