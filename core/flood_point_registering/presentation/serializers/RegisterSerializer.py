from django.utils import timezone
from rest_framework import serializers
from core.flood_point_registering.infra.models import Flood_Point_Register
from core.addressing.infra.models import City, Neighborhood
from django.db import models
from uuid import UUID


class FloodPointRegisterSerializer(serializers.ModelSerializer):
    """Serializer for Flood Point Register.

    - Writeable fields: city (pk), neighborhood (pk), possibility (float), finished_at, props (JSON)
    - Read-only helpers: city_name, neighborhood_name
    - Validations: possibility 0..1, created_at <= finished_at
    """

    # Read-only helper fields for client convenience
    city_name = serializers.CharField(source="city.name", read_only=True)
    neighborhood_name = serializers.CharField(
        source="neighborhood.name", read_only=True
    )
    # Require props and validate as GeoJSON Feature
    props = serializers.JSONField()

    class Meta:
        model = Flood_Point_Register
        fields = [
            "id",
            "city",
            "city_name",
            "neighborhood",
            "neighborhood_name",
            "possibility",
            "created_at",
            "finished_at",
            "props",
        ]
        extra_kwargs = {
            # props pode ser omitido/nulo; será padronizado para um Feature básico
            "props": {"required": False, "allow_null": True},
            # allow API to omit timestamps; we'll default them
            "created_at": {"read_only": True},
            # finished_at deve ser enviado na requisição (sem padrão de 2h)
            "finished_at": {"required": True, "allow_null": False},
            # possibility pode vir nulo e será defaultado para 0.0
            "possibility": {"required": False, "allow_null": True},
        }

    def to_internal_value(self, data):
        """Accept city and neighborhood by name strings; default possibility/props."""
        mutable = data.copy()

        # Resolve City from name if provided as string
        city_input = mutable.get("city")
        resolved_city = None
        if (
            isinstance(city_input, str)
            and city_input.strip()
            and not self._is_uuid(city_input)
        ):
            resolved_city = City.objects.filter(name__iexact=city_input.strip()).first()
            if not resolved_city:
                raise serializers.ValidationError({"city": "cidade não encontrada"})
            # Pass PK so PrimaryKeyRelatedField can bind
            mutable["city"] = str(resolved_city.pk)

        # Resolve Neighborhood from name; prefer matching the resolved city when available
        nb_input = mutable.get("neighborhood")
        if (
            isinstance(nb_input, str)
            and nb_input.strip()
            and not self._is_uuid(nb_input)
        ):
            nb_qs = Neighborhood.objects.filter(name__iexact=nb_input.strip())
            if resolved_city is not None:
                nb_qs = nb_qs.filter(
                    # Prefer link via city_ref when present; fallback to textual city if needed
                    models.Q(city_ref_id=resolved_city.id)
                    | models.Q(city__iexact=resolved_city.name)
                )
            nb = nb_qs.first()
            if not nb:
                raise serializers.ValidationError(
                    {"neighborhood": "bairro não encontrado para a cidade informada"}
                )
            mutable["neighborhood"] = str(nb.pk)

        # Default possibility if null/empty -> 0.0
        poss = mutable.get("possibility", None)
        if poss in (None, ""):
            mutable["possibility"] = 0.0

        # Keep absent spatial evidence explicit; never invent a real-world point.
        props = mutable.get("props", None)
        if props in (None, ""):
            mutable["props"] = {
                "type": "Feature",
                "geometry": None,
                "properties": {},
            }

        return super().to_internal_value(mutable)

    @staticmethod
    def _is_uuid(value):
        try:
            UUID(str(value))
        except (TypeError, ValueError, AttributeError):
            return False
        return True

    def validate_possibility(self, value: float) -> float:
        # Accept probability in [0,1]. If 1<value<=100, interpret as percentage.
        v = float(value)
        if 0 <= v <= 1:
            return v
        if 1 < v <= 100:
            return round(v / 100.0, 6)
        raise serializers.ValidationError(
            "possibility deve estar no intervalo [0, 1] ou percentual até 100"
        )

    def validate(self, attrs):
        # Validate timestamps; created_at is handled by model auto_now_add
        created_at = attrs.get("created_at") or getattr(
            self.instance, "created_at", None
        )
        if created_at is None:
            # We'll compute finished_at relative to now, but won't set created_at explicitly
            created_at = timezone.now()

        # finished_at must be provided by the request; no default window
        finished_at = attrs.get("finished_at") or getattr(
            self.instance, "finished_at", None
        )
        if finished_at is None:
            raise serializers.ValidationError(
                {"finished_at": "finished_at é obrigatório e deve ser informado"}
            )
        if created_at and finished_at and created_at > finished_at:
            raise serializers.ValidationError(
                {"finished_at": "finished_at deve ser maior ou igual a created_at"}
            )
        # Optional: ensure neighborhood belongs to same city if Neighborhood has city_ref
        city = attrs.get("city") or getattr(self.instance, "city", None)
        neighborhood = attrs.get("neighborhood") or getattr(
            self.instance, "neighborhood", None
        )
        if city and neighborhood and getattr(neighborhood, "city_ref_id", None):
            if neighborhood.city_ref_id != getattr(city, "id", None):
                raise serializers.ValidationError(
                    {"neighborhood": "neighborhood não pertence à cidade informada"}
                )
        return attrs
