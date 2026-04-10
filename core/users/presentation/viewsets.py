from rest_framework import status, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.users.presentation.serializers import (
    UserSerializer,
    SignupSerializer,
)
from core.users.infra.models import User as DjangoUser
from core.users.presentation.auth_views import generate_tokens_for_user
from core.uploader.infra.django_storage_uploader import DjangoStorageUploader
from core.uploader.application.services import UploadBinaryService


class UsersViewSet(viewsets.ViewSet):
    """Auth-related endpoints grouped under a router.

    Routes:
      - POST /users/signup
      - GET  /users/me
    """

    permission_classes = [permissions.AllowAny]

    @action(
        detail=False,
        methods=["post"],
        url_path="signup",
        permission_classes=[permissions.AllowAny],
    )
    def signup(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].lower().strip()
        if DjangoUser.objects.filter(email=email).exists():
            return Response(
                {"detail": "E-mail já cadastrado."}, status=status.HTTP_400_BAD_REQUEST
            )

        user = DjangoUser(name=serializer.validated_data["name"], email=email)
        user.set_password(serializer.validated_data["password"])

        # Optional profile picture file -> upload and set URL
        pic = serializer.validated_data.get("profile_picture")
        if pic:
            data = pic.read()
            path = f"users/{email}/profile/{pic.name}"
            svc = UploadBinaryService(DjangoStorageUploader(base_dir="uploads"))
            result = svc.execute(
                data=data, path=path, content_type=getattr(pic, "content_type", None)
            )
            user.profile_picture = result.url

        user.save()
        tokens = generate_tokens_for_user(user)
        return Response(
            {"user": UserSerializer(user).data, "tokens": tokens},
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[permissions.IsAuthenticated],
    )
    def me(self, request):
        u: DjangoUser = request.user
        data = {
            "id": str(u.id),
            "name": u.name,
            "type": u.type,
            "email": u.email,
            "profile_picture": u.profile_picture,
        }
        return Response(data, status=status.HTTP_200_OK)
