from rest_framework import serializers

from core.addressing.models import Region

from .models import PushDelivery, PushSubscription, RegionSubscription


class RegionSummarySerializer(serializers.ModelSerializer):
    city = serializers.SerializerMethodField()

    @staticmethod
    def get_city(region):
        return {
            "id": str(region.city_ref_id) if region.city_ref_id else "",
            "name": region.city,
        }

    class Meta:
        model = Region
        fields = ("id", "name", "city")


class RegionSubscriptionSerializer(serializers.ModelSerializer):
    region_id = serializers.PrimaryKeyRelatedField(
        source="region", queryset=Region.objects.filter(is_active=True), write_only=True
    )
    region = RegionSummarySerializer(read_only=True)

    class Meta:
        model = RegionSubscription
        fields = ("id", "region_id", "region", "created_at")
        read_only_fields = ("id", "created_at")


class RegionSubscriptionDeleteSerializer(serializers.Serializer):
    region_id = serializers.PrimaryKeyRelatedField(
        source="region", queryset=Region.objects.all()
    )


class PushSubscriptionSerializer(serializers.ModelSerializer):
    endpoint = serializers.URLField(max_length=2048, write_only=True)
    keys = serializers.DictField(write_only=True)

    class Meta:
        model = PushSubscription
        fields = ("id", "endpoint", "keys", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "is_active", "created_at", "updated_at")

    def validate_keys(self, value):
        p256dh = value.get("p256dh")
        auth = value.get("auth")
        if not isinstance(p256dh, str) or not p256dh.strip():
            raise serializers.ValidationError({"p256dh": "Chave obrigatória."})
        if not isinstance(auth, str) or not auth.strip():
            raise serializers.ValidationError({"auth": "Chave obrigatória."})
        if len(p256dh) > 512 or len(auth) > 512:
            raise serializers.ValidationError("Chave excede o tamanho permitido.")
        return value

    def create(self, validated_data):
        keys = validated_data.pop("keys")
        request = self.context["request"]
        subscription, _ = PushSubscription.objects.update_or_create(
            endpoint=validated_data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": keys["p256dh"],
                "auth": keys["auth"],
                "user_agent": request.headers.get("User-Agent", "")[:512],
                "is_active": True,
                "expired_at": None,
            },
        )
        return subscription


class PushSubscriptionDeleteSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=2048)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ResolveSerializer(ReasonSerializer):
    notify_subscribers = serializers.BooleanField(default=True)


class PushDeliverySummarySerializer(serializers.Serializer):
    pending = serializers.IntegerField()
    sent = serializers.IntegerField()
    failed = serializers.IntegerField()
    expired = serializers.IntegerField()


class OperationalAlertFilterSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("OPEN_INDICATION", "CONFIRMED", "DISMISSED", "RESOLVED"),
        required=False,
    )
    region = serializers.UUIDField(required=False)
    camera = serializers.UUIDField(required=False)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    region_id = serializers.UUIDField(required=False)
    camera_id = serializers.UUIDField(required=False)
    detected_from = serializers.DateTimeField(required=False)
    detected_to = serializers.DateTimeField(required=False)
    ordering = serializers.ChoiceField(
        choices=("first_detected_at", "-first_detected_at", "last_detected_at", "-last_detected_at"),
        required=False,
    )

    def validate(self, attrs):
        attrs["region"] = attrs.get("region_id", attrs.get("region"))
        attrs["camera"] = attrs.get("camera_id", attrs.get("camera"))
        attrs["date_from"] = attrs.get("detected_from", attrs.get("date_from"))
        attrs["date_to"] = attrs.get("detected_to", attrs.get("date_to"))
        if attrs.get("date_from") and attrs.get("date_to") and attrs["date_from"] > attrs["date_to"]:
            raise serializers.ValidationError("date_from deve ser anterior a date_to.")
        return attrs
