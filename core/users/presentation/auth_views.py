from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.users.serializers.auth_serializer import (
    AppTokenRefreshSerializer,
    EmailTokenObtainPairSerializer,
)

class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class AppTokenRefreshView(TokenRefreshView):
    serializer_class = AppTokenRefreshSerializer
