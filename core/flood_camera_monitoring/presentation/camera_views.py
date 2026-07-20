from datetime import timedelta
import unicodedata
from uuid import UUID

from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import connections, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response

from core.flood_camera_monitoring.presentation.serializers import (
    CameraCreateSerializer,
    CameraListSerializer,
    CameraReadSerializer,
    NearbyCamerasQuerySerializer,
    StreamSnapshotSerializer,
    StreamBatchSerializer,
    build_legacy_prediction_payload,
    normalize_hls_url,
    operational_stale_after_seconds,
)
from django.conf import settings
from core.flood_camera_monitoring.presentation.utils import build_prediction_payload
from core.addressing.models import (
    Address,
    AddressReference,
    City,
    GeodataDataset,
    Neighborhood,
    Street,
)
from core.addressing.geojson import point_inside_geometry
from core.flood_camera_monitoring.services.nearby import (
    MissingCameraCoordinates,
    find_nearby_cameras,
)
from core.flood_camera_monitoring.services.territorial_context import apply_camera_territorial_context
from core.addressing.services import TerritoryResolutionError
from core.flood_camera_monitoring.infra.models import (
    Camera,
    CameraOperationalSnapshot,
)
from core.users.permissions import IsAppAdmin
import uuid
from config.pagination import DefaultPageNumberPagination
from core.common.mixins import SafeOrderingMixin


def _camera_metadata_queryset():
    return Camera.objects.select_related(
        "address",
        "address__city_ref",
        "address__neighborhood",
        "address__neighborhood__region",
        "neighborhood",
        "neighborhood__region",
        "operational_snapshot",
        "created_by",
        "city",
        "region",
        "street",
        "road_segment",
        "address_reference",
    )


def _parse_uuid_filter(value, field_name):
    if not value:
        return None, None
    try:
        return UUID(str(value)), None
    except (ValueError, TypeError, AttributeError):
        return None, Response(
            {field_name: [f"{field_name} inválido."]},
            status=status.HTTP_400_BAD_REQUEST,
        )


def _normalized_address_text(value):
    return " ".join(
        unicodedata.normalize("NFKD", value or "")
        .encode("ascii", "ignore")
        .decode()
        .casefold()
        .split()
    )


class NearbyCamerasPagination(DefaultPageNumberPagination):
    page_size = 6
    max_page_size = 20
    radius_m = 5_000

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["ordering"] = "distance"
        response.data["radius_m"] = self.radius_m
        return response


def _snapshot_prediction_response(request, view):
    queryset = _camera_metadata_queryset().filter(status=Camera.CameraStatus.ACTIVE)
    stale_before = timezone.now() - timedelta(
        seconds=operational_stale_after_seconds()
    )
    queryset = _with_operational_priority(queryset, stale_before).order_by(
        "_operational_priority", "description"
    )
    payload = [build_legacy_prediction_payload(camera) for camera in queryset]
    paginator = DefaultPageNumberPagination()
    page_items = paginator.paginate_queryset(payload, request, view=view)
    return paginator.get_paginated_response(page_items)


def _with_operational_priority(queryset, stale_before):
    valid_prediction = Q(
        operational_snapshot__analysis_status=(
            CameraOperationalSnapshot.AnalysisStatus.AVAILABLE
        ),
        operational_snapshot__analyzed_at__gt=stale_before,
        operational_snapshot__model_status=(
            CameraOperationalSnapshot.ModelStatus.READY
        ),
        operational_snapshot__frames__gt=0,
        operational_snapshot__prob_normal__isnull=False,
        operational_snapshot__prob_medium__isnull=False,
        operational_snapshot__prob_flooded__isnull=False,
        operational_snapshot__confidence__isnull=False,
        operational_snapshot__prob_normal__gte=0.0,
        operational_snapshot__prob_normal__lte=100.0,
        operational_snapshot__prob_medium__gte=0.0,
        operational_snapshot__prob_medium__lte=100.0,
        operational_snapshot__prob_flooded__gte=0.0,
        operational_snapshot__prob_flooded__lte=100.0,
        operational_snapshot__confidence__gte=0.0,
        operational_snapshot__confidence__lte=100.0,
        operational_snapshot__model_version__isnull=False,
    ) & ~Q(operational_snapshot__model_version="")
    failure_or_stale = (
        Q(
            operational_snapshot__analysis_status__in=[
                CameraOperationalSnapshot.AnalysisStatus.STALE,
                CameraOperationalSnapshot.AnalysisStatus.NO_FRAME,
                CameraOperationalSnapshot.AnalysisStatus.MODEL_UNAVAILABLE,
                CameraOperationalSnapshot.AnalysisStatus.ERROR,
            ]
        )
        | Q(
            operational_snapshot__analysis_status=(
                CameraOperationalSnapshot.AnalysisStatus.AVAILABLE
            ),
            operational_snapshot__analyzed_at__lte=stale_before,
        )
        | Q(
            operational_snapshot__model_status__in=[
                CameraOperationalSnapshot.ModelStatus.UNAVAILABLE,
                CameraOperationalSnapshot.ModelStatus.FALLBACK,
            ]
        )
        | Q(
            operational_snapshot__stream_status=(
                CameraOperationalSnapshot.StreamStatus.UNAVAILABLE
            )
        )
    )
    return queryset.annotate(
        _operational_priority=Case(
            When(status=Camera.CameraStatus.INACTIVE, then=Value(6)),
            When(
                valid_prediction
                & Q(
                    operational_snapshot__classification=(
                        CameraOperationalSnapshot.CameraClassification.FLOOD_INDICATION
                    )
                ),
                then=Value(1),
            ),
            When(
                valid_prediction
                & Q(
                    operational_snapshot__classification=(
                        CameraOperationalSnapshot.CameraClassification.INTERMEDIATE_INDICATION
                    )
                ),
                then=Value(2),
            ),
            When(failure_or_stale, then=Value(3)),
            When(
                valid_prediction
                & Q(
                    operational_snapshot__classification=(
                        CameraOperationalSnapshot.CameraClassification.NO_INDICATION
                    )
                ),
                then=Value(4),
            ),
            default=Value(5),
            output_field=IntegerField(),
        )
    )


class CameraMetadataViewSet(SafeOrderingMixin, viewsets.ViewSet):
    """API leve de metadados; não importa nem executa captura ou inferência."""

    ordering_map = {
        "operational": "_operational_priority",
        "description": "description",
        "created_at": "created_at",
        "updated_at": "updated_at",
        "status": "status",
        "neighborhood": "address__neighborhood__name",
        "region": "address__neighborhood__region__name",
        "latitude": "address__latitude",
        "longitude": "address__longitude",
    }
    default_ordering = ["_operational_priority", "description"]

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsAppAdmin()]
        return [permissions.AllowAny()]

    def list(self, request):
        queryset = _camera_metadata_queryset()
        search = str(request.query_params.get("search", "")).strip()
        if search:
            queryset = queryset.filter(
                Q(description__icontains=search)
                | Q(address__street__icontains=search)
                | Q(address__city__icontains=search)
                | Q(address__neighborhood__name__icontains=search)
                | Q(neighborhood__name__icontains=search)
            )

        neighborhood_id, error = _parse_uuid_filter(
            request.query_params.get("neighborhood_id"), "neighborhood_id"
        )
        if error:
            return error
        if neighborhood_id:
            queryset = queryset.filter(
                Q(address__neighborhood_id=neighborhood_id)
                | Q(address__isnull=True, neighborhood_id=neighborhood_id)
            )

        region_id, error = _parse_uuid_filter(
            request.query_params.get("region_id"), "region_id"
        )
        if error:
            return error
        if region_id:
            queryset = queryset.filter(
                Q(address__neighborhood__region_id=region_id)
                | Q(address__isnull=True, neighborhood__region_id=region_id)
            )

        administrative_status = request.query_params.get("administrative_status")
        if administrative_status:
            administrative_status = str(administrative_status).upper()
            if administrative_status == "ACTIVE":
                queryset = queryset.filter(
                    status__in=[Camera.CameraStatus.ACTIVE, Camera.CameraStatus.OFFLINE]
                )
            elif administrative_status == "INACTIVE":
                queryset = queryset.filter(status=Camera.CameraStatus.INACTIVE)
            else:
                return Response(
                    {
                        "administrative_status": [
                            "Use ACTIVE ou INACTIVE."
                        ]
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        stream_status = request.query_params.get("stream_status")
        if stream_status:
            stream_status = str(stream_status).upper()
            valid_stream_statuses = {
                choice
                for choice, _ in CameraOperationalSnapshot.StreamStatus.choices
            }
            if stream_status not in valid_stream_statuses:
                return Response(
                    {"stream_status": ["Estado operacional inválido."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(
                operational_snapshot__stream_status=stream_status
            )

        stale_before = timezone.now() - timedelta(
            seconds=operational_stale_after_seconds()
        )
        analysis_status = request.query_params.get("analysis_status")
        if analysis_status:
            analysis_status = str(analysis_status).upper()
            valid_analysis_statuses = {
                choice
                for choice, _ in CameraOperationalSnapshot.AnalysisStatus.choices
            }
            if analysis_status not in valid_analysis_statuses:
                return Response(
                    {"analysis_status": ["Estado de análise inválido."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if analysis_status == CameraOperationalSnapshot.AnalysisStatus.STALE:
                queryset = queryset.filter(
                    Q(operational_snapshot__analysis_status=analysis_status)
                    | Q(
                        operational_snapshot__analysis_status=(
                            CameraOperationalSnapshot.AnalysisStatus.AVAILABLE
                        ),
                        operational_snapshot__analyzed_at__lte=stale_before,
                    )
                )
            elif analysis_status == CameraOperationalSnapshot.AnalysisStatus.AVAILABLE:
                queryset = queryset.filter(
                    operational_snapshot__analysis_status=analysis_status,
                    operational_snapshot__analyzed_at__gt=stale_before,
                )
            else:
                queryset = queryset.filter(
                    operational_snapshot__analysis_status=analysis_status
                )

        classification = request.query_params.get("classification")
        if classification:
            classification = str(classification).upper()
            valid_classifications = {
                choice
                for choice, _ in CameraOperationalSnapshot.CameraClassification.choices
            }
            if classification not in valid_classifications:
                return Response(
                    {"classification": ["Classificação inválida."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(
                operational_snapshot__analysis_status=(
                    CameraOperationalSnapshot.AnalysisStatus.AVAILABLE
                ),
                operational_snapshot__analyzed_at__gt=stale_before,
                operational_snapshot__model_status=(
                    CameraOperationalSnapshot.ModelStatus.READY
                ),
                operational_snapshot__classification=classification,
                operational_snapshot__frames__gt=0,
                operational_snapshot__prob_normal__isnull=False,
                operational_snapshot__prob_medium__isnull=False,
                operational_snapshot__prob_flooded__isnull=False,
                operational_snapshot__confidence__isnull=False,
                operational_snapshot__prob_normal__gte=0.0,
                operational_snapshot__prob_normal__lte=100.0,
                operational_snapshot__prob_medium__gte=0.0,
                operational_snapshot__prob_medium__lte=100.0,
                operational_snapshot__prob_flooded__gte=0.0,
                operational_snapshot__prob_flooded__lte=100.0,
                operational_snapshot__confidence__gte=0.0,
                operational_snapshot__confidence__lte=100.0,
                operational_snapshot__model_version__isnull=False,
            ).exclude(operational_snapshot__model_version="")

        ordering = request.query_params.get("ordering")
        queryset = _with_operational_priority(queryset.distinct(), stale_before)
        queryset = self.apply_ordering(queryset, ordering)
        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        data = CameraListSerializer(page, many=True).data
        return paginator.get_paginated_response(data)

    def retrieve(self, request, pk=None):
        try:
            camera_id = UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"detail": "Câmera não encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        camera = _camera_metadata_queryset().filter(pk=camera_id).first()
        if camera is None:
            return Response(
                {"detail": "Câmera não encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        include_created_by = IsAppAdmin().has_permission(request, self)
        return Response(
            CameraReadSerializer(
                camera,
                context={
                    "include_created_by": include_created_by,
                    "include_inactive_sources": include_created_by,
                },
            ).data
        )

    def nearby(self, request, pk=None):
        query = NearbyCamerasQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        parameters = query.validated_data

        try:
            camera_id = UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {"detail": "Câmera não encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        origin = _camera_metadata_queryset().filter(pk=camera_id).first()
        if origin is None:
            return Response(
                {"detail": "Câmera não encontrada."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            nearby_cameras = find_nearby_cameras(
                origin=origin,
                candidates=_camera_metadata_queryset(),
                radius_m=parameters["radius_m"],
            )
        except MissingCameraCoordinates:
            return Response(
                {
                    "code": "camera_location_unavailable",
                    "detail": "A câmera de origem não possui coordenadas válidas.",
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        paginator = NearbyCamerasPagination()
        paginator.radius_m = parameters["radius_m"]
        page = paginator.paginate_queryset(nearby_cameras, request, view=self)
        data = []
        for result in page:
            item = dict(CameraListSerializer(result.camera).data)
            item["distance_m"] = round(result.distance_m)
            data.append(item)
        return paginator.get_paginated_response(data)

    def create(self, request):
        serializer = CameraCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        address_data = data["address"]

        city = City.objects.filter(pk=address_data["city_id"]).first()
        if city is None:
            return Response(
                {"address": {"city_id": ["Cidade não encontrada."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        neighborhood = Neighborhood.objects.select_related("city_ref").filter(
            pk=address_data["neighborhood_id"]
        ).first()
        if neighborhood is None:
            return Response(
                {"address": {"neighborhood_id": ["Bairro não encontrado."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (
            neighborhood.city_ref_id
            and neighborhood.city_ref_id != city.id
        ) or (
            not neighborhood.city_ref_id
            and neighborhood.city.strip().casefold() != city.name.strip().casefold()
        ):
            return Response(
                {
                    "address": {
                        "neighborhood_id": [
                            "O bairro não pertence à cidade informada."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_street = None
        address_reference = None
        street_id = address_data.get("street_id")
        address_reference_id = address_data.get("address_reference_id")

        if address_reference_id:
            address_reference = AddressReference.objects.select_related(
                "city", "neighborhood", "street", "dataset"
            ).filter(
                pk=address_reference_id,
                is_active=True,
                dataset__status=GeodataDataset.Status.ACTIVE,
            ).first()
            if address_reference is None:
                return Response(
                    {
                        "address": {
                            "address_reference_id": [
                                "Referência de endereço não encontrada ou inativa."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if address_reference.city_id != city.id:
                return Response(
                    {
                        "address": {
                            "address_reference_id": [
                                "A referência de endereço não pertence à cidade informada."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if (
                address_reference.neighborhood_id
                and address_reference.neighborhood_id != neighborhood.id
            ):
                # A referência canônica é mais específica que o bairro
                # inferido pelo ponto. A cidade já foi validada acima; usar o
                # bairro da referência evita rejeição por divergência cadastral.
                neighborhood = address_reference.neighborhood
            reference_street = address_reference.street
            if reference_street and (
                reference_street.city_id != city.id
                or not reference_street.is_active
                or reference_street.dataset.status != GeodataDataset.Status.ACTIVE
            ):
                return Response(
                    {
                        "address": {
                            "address_reference_id": [
                                "A rua vinculada à referência está inativa ou inconsistente."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            selected_street = reference_street
            if street_id:
                explicit_street = Street.objects.select_related("dataset").filter(
                    pk=street_id,
                    city=city,
                    is_active=True,
                    dataset__status=GeodataDataset.Status.ACTIVE,
                ).first()
                if (
                    explicit_street is None
                    or explicit_street.normalized_name
                    != _normalized_address_text(address_reference.street_name)
                ):
                    return Response(
                        {
                            "address": {
                                "street_id": [
                                    "A rua não corresponde à referência de endereço informada."
                                ]
                            }
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                selected_street = explicit_street

        if street_id and selected_street is None:
            selected_street = Street.objects.select_related("dataset").filter(
                pk=street_id,
                city=city,
                is_active=True,
                dataset__status=GeodataDataset.Status.ACTIVE,
            ).first()
            if selected_street is None:
                return Response(
                    {
                        "address": {
                            "street_id": [
                                "Rua não encontrada, inativa ou incompatível com a cidade."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if selected_street and (not address_reference or street_id):
            linked_neighborhoods = selected_street.neighborhood_links.all()
            if linked_neighborhoods.exists() and not linked_neighborhoods.filter(
                neighborhood=neighborhood
            ).exists():
                return Response(
                    {
                        "address": {
                            "street_id": [
                                "A rua não está associada ao bairro informado."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if address_reference and not address_reference.neighborhood_id:
            reference_match = point_inside_geometry(
                address_reference.location.x,
                address_reference.location.y,
                neighborhood.geometry,
            )
            if reference_match is False:
                return Response(
                    {
                        "address": {
                            "address_reference_id": [
                                "A coordenada da referência está fora do bairro informado."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        longitude = address_data["longitude"]
        latitude = address_data["latitude"]
        if longitude == 0 and latitude == 0:
            return Response(
                {
                    "address": {
                        "coordinates": [
                            "[0,0] não representa uma localização operacional resolvida."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if address_reference and not AddressReference.objects.filter(
            pk=address_reference.pk,
            location__distance_lte=(
                Point(longitude, latitude, srid=4326),
                D(
                    m=getattr(
                        settings,
                        "ADDRESS_REFERENCE_COORDINATE_TOLERANCE_METERS",
                        5,
                    )
                ),
            ),
        ).exists():
            return Response(
                {
                    "address": {
                        "address_reference_id": [
                            "As coordenadas não correspondem à referência de endereço selecionada."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            neighborhood_match = point_inside_geometry(
                longitude, latitude, neighborhood.geometry
            )
            city_match = point_inside_geometry(longitude, latitude, city.geometry)
        except ValueError as exc:
            return Response(
                {"address": {"coordinates": [str(exc)]}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if neighborhood_match is False:
            return Response(
                {
                    "address": {
                        "coordinates": [
                            "As coordenadas informadas estão fora do polígono do bairro."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if city_match is False:
            return Response(
                {
                    "address": {
                        "coordinates": [
                            "As coordenadas informadas estão fora do polígono da cidade."
                        ]
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_hls = data["video_hls"]
        with transaction.atomic():
            existing_streams = Camera.objects.select_for_update().exclude(
                video_hls__isnull=True
            ).exclude(video_hls="")
            duplicate = any(
                normalize_hls_url(value) == normalized_hls
                for value in existing_streams.values_list("video_hls", flat=True)
            )
            if duplicate:
                return Response(
                    {
                        "detail": "Já existe uma câmera com este stream HLS.",
                        "video_hls": ["Stream HLS já cadastrado."],
                    },
                    status=status.HTTP_409_CONFLICT,
                )

            canonical_street = (
                address_reference.street_name
                if address_reference
                else selected_street.name
                if selected_street
                else address_data["street"].strip()
            )
            canonical_number = (
                address_reference.number
                if address_reference
                else address_data.get("number", "").strip()
            )
            canonical_zipcode = (
                address_reference.zipcode
                if address_reference
                else address_data.get("zipcode", "").strip()
            )
            address = Address.objects.create(
                street=canonical_street,
                number=canonical_number,
                city=city.name,
                city_ref=city,
                street_ref=selected_street,
                address_reference=address_reference,
                dataset=(
                    address_reference.dataset
                    if address_reference
                    else selected_street.dataset
                    if selected_street
                    else None
                ),
                source_record_id=(
                    address_reference.source_record_id
                    if address_reference
                    else selected_street.source_record_id
                    if selected_street
                    else ""
                ),
                state=address_data.get("state", "").strip(),
                country=address_data.get("country", "Brazil").strip(),
                zipcode=canonical_zipcode,
                latitude=address_data["latitude"],
                longitude=address_data["longitude"],
                neighborhood=neighborhood,
            )
            camera = Camera.objects.create(
                description=data["description"].strip(),
                video_hls=normalized_hls,
                video_embed=data.get("video_embed") or None,
                address=address,
                created_by=request.user,
                # Escrita dupla transitória para consumidores legados.
                neighborhood=neighborhood,
                latitude=address.latitude,
                longitude=address.longitude,
            )
            try:
                apply_camera_territorial_context(
                    camera, latitude=address.latitude, longitude=address.longitude
                )
            except TerritoryResolutionError:
                # A validação legada de cidade/bairro permanece válida mesmo
                # quando a nova base territorial ainda não foi carregada.
                camera.city = city
                camera.region = neighborhood.region
                camera.street = selected_street
                camera.address_reference = address_reference
                camera.territory_resolution = {"method": "LEGACY_ADDRESS", "resolved": False}
            camera.save(update_fields=[
                "city", "region", "neighborhood", "street", "road_segment",
                "address_reference", "territory_resolution", "updated_at",
            ])
            CameraOperationalSnapshot.objects.create(camera=camera)

        camera = _camera_metadata_queryset().get(pk=camera.pk)
        return Response(
            CameraReadSerializer(
                camera,
                context={
                    "include_created_by": True,
                    "include_inactive_sources": True,
                },
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def predict_all(self, request):
        return _snapshot_prediction_response(request, self)
