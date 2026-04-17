from rest_framework_simplejwt.views import TokenObtainPairView

from core.users.serializers.auth_serializer import EmailTokenObtainPairSerializer


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
