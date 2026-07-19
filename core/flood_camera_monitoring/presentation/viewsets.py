from datetime import timedelta
import unicodedata
from uuid import UUID

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
from core.addressing.infra.models import (
    Address,
    AddressReference,
    City,
    GeodataDataset,
    Neighborhood,
    Street,
)
from core.addressing.geojson import point_inside_geometry
from core.flood_camera_monitoring.application.nearby_cameras import (
    MissingCameraCoordinates,
    find_nearby_cameras,
)
from core.flood_camera_monitoring.infra.models import (
    Camera,
    CameraOperationalSnapshot,
)
from core.users.permissions import IsAppAdmin
import uuid
from config.pagination import DefaultPageNumberPagination
from core.common.mixins import SafeOrderingMixin
from pathlib import Path
import os
import redis
from django.http import Http404
import time
import subprocess
import shlex
from core.flood_camera_monitoring.infra.utils import (
    resolve_checkpoint_path,
    looks_like_lfs_pointer,
)


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
                return Response(
                    {
                        "address": {
                            "address_reference_id": [
                                "A referência de endereço não pertence ao bairro informado."
                            ]
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
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

        if selected_street and not address_reference:
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


class FloodMonitoringViewSet(SafeOrderingMixin, viewsets.ViewSet):
    # Ordering config for cameras list
    ordering_map = {
        "description": "description",
        "created_at": "created_at",
        "updated_at": "updated_at",
        "status": "status",
        "neighborhood": "neighborhood__name",
        "region": "neighborhood__region__name",
        "latitude": "latitude",
        "longitude": "longitude",
    }
    default_ordering = "description"

    # Legacy POST handler removed; use explicit actions below

    @action(detail=False, methods=["get"], url_path="predict/all")
    def predict_all(self, request):
        return _snapshot_prediction_response(request, self)

    @action(detail=False, methods=["post"], url_path="predict/snapshot")
    def predict_snapshot(self, request):
        from core.flood_camera_monitoring.adapters.gateways.opencv_stream_adapter import (
            OpenCVVideoStream,
        )
        from core.flood_camera_monitoring.application.dto.snapshot_request import (
            SnapshotDetectRequest,
        )
        from core.flood_camera_monitoring.application.use_cases.detect_flood_snapshot_from_stream import (
            DetectFloodSnapshotFromStream,
        )
        from core.flood_camera_monitoring.infra.torch_flood_classifier import (
            build_default_classifier,
        )

        serializer = StreamSnapshotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        clf = build_default_classifier()
        stream = OpenCVVideoStream(data["stream_url"])  # implements VideoStreamPort
        service = DetectFloodSnapshotFromStream(classifier=clf, stream=stream)
        try:
            res = service.execute(
                SnapshotDetectRequest(
                    timeout_seconds=float(data.get("timeout_seconds", 5.0))
                )
            )
        except TimeoutError:
            return Response(
                {"detail": "Could not capture frame"},
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )

        return Response(build_prediction_payload(res))

    @action(detail=False, methods=["post"], url_path="predict/batch")
    def predict_batch(self, request):
        from core.flood_camera_monitoring.adapters.gateways.opencv_stream_adapter import (
            OpenCVVideoStream,
        )
        from core.flood_camera_monitoring.application.dto.stream_request import (
            StreamDetectRequest,
        )
        from core.flood_camera_monitoring.application.use_cases.detect_flood_from_stream import (
            DetectFloodFromStream,
        )
        from core.flood_camera_monitoring.infra.torch_flood_classifier import (
            build_default_classifier,
        )

        serializer = StreamBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        clf = build_default_classifier()
        stream = OpenCVVideoStream(data["stream_url"])  # VideoStreamPort
        service = DetectFloodFromStream(classifier=clf, stream=stream)
        req = StreamDetectRequest(
            stream_url=data["stream_url"],
            interval_seconds=float(data.get("interval_seconds", 2.0)),
            max_iterations=int(data.get("max_iterations", 3)),
        )

        results = [build_prediction_payload(res) for res in service.run(req)]

        return Response({"results": results})

    @action(detail=False, methods=["post"], url_path="analyze/all")
    def analyze_all(self, request):
        from core.flood_camera_monitoring.application.use_cases.analyze_all_cameras import (
            AnalyzeAllCamerasService,
        )

        service = AnalyzeAllCamerasService()
        saved = service.run()
        return Response({"saved": saved})

    @action(detail=False, methods=["get"], url_path="cameras")
    def cameras(self, request):
        neighborhood_id = request.query_params.get("neighborhood_id")
        region_id = request.query_params.get("region_id")
        neighborhood_name = request.query_params.get("neighborhood")
        ordering_param = request.query_params.get("ordering", "description")

        qs = Camera.objects.select_related("neighborhood", "neighborhood__region").all()

        if neighborhood_id:
            try:
                nb_uuid = uuid.UUID(str(neighborhood_id))
                qs = qs.filter(neighborhood_id=nb_uuid)
            except (ValueError, AttributeError):
                return Response(
                    {"detail": "neighborhood_id inválido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if region_id:
            try:
                rg_uuid = uuid.UUID(str(region_id))
                qs = qs.filter(neighborhood__region_id=rg_uuid)
            except (ValueError, AttributeError):
                return Response(
                    {"detail": "region_id inválido"}, status=status.HTTP_400_BAD_REQUEST
                )

        if neighborhood_name:
            qs = qs.filter(neighborhood__name__icontains=neighborhood_name)

        qs = self.apply_ordering(qs, ordering_param)

        paginator = DefaultPageNumberPagination()
        page_items = paginator.paginate_queryset(qs, request, view=self)

        data_out = []
        for cam in page_items:
            nb = cam.neighborhood
            rg = nb.region if nb else None
            data_out.append(
                {
                    "id": str(cam.id),
                    "description": cam.description,
                    "status": cam.get_status_display(),
                    "video_hls": cam.video_hls,
                    "video_embed": cam.video_embed,
                    "neighborhood": (
                        {"id": str(nb.id), "name": nb.name} if nb else None
                    ),
                    "region": ({"id": str(rg.id), "name": rg.name} if rg else None),
                    "latitude": cam.latitude,
                    "longitude": cam.longitude,
                }
            )

        # get_paginated_response will include count/next/previous and ordering
        return paginator.get_paginated_response(data_out)


## Removed duplicate StreamBatchDetectView; use ViewSet action predict/batch


# =====================
# HLS live loop helpers
# =====================


def _media_loop_url() -> str | None:
    root = Path(settings.MEDIA_ROOT)
    files = sorted([p.name for p in root.glob("*.mp4")])
    if not files:
        return None
    items = [f"media:{name}" for name in files]
    return "loop:" + ",".join(items)


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _ensure_hls_live_loop() -> tuple[bool, str | None, str | None]:
    """Ensure an ffmpeg process is producing a looping HLS stream from media/*.mp4.

    Returns (ok, playlist_path, error).
    - playlist_path is absolute filesystem path to playlist.m3u8 (not URL)
    """
    media_root = Path(settings.MEDIA_ROOT)
    src_files = sorted([p for p in media_root.glob("*.mp4")])
    if not src_files:
        return False, None, "No .mp4 files in MEDIA_ROOT"

    out_dir = media_root / "hls" / "live"
    _ensure_dir(out_dir)
    concat_list = out_dir / "list.txt"
    source_mp4 = out_dir / "source.mp4"
    playlist = out_dir / "playlist.m3u8"
    pid_file = out_dir / "ffmpeg.pid"

    # 1) Build concat list for joining
    try:
        with concat_list.open("w", encoding="utf-8") as fh:
            for p in src_files:
                fh.write(f"file '{p.as_posix()}'\n")
    except Exception as e:
        return False, None, f"Failed to write concat list: {e}"

    # 2) If no source.mp4, build by concatenating (stream copy if possible)
    if not source_mp4.exists():
        cmd_copy = f"ffmpeg -y -f concat -safe 0 -i {shlex.quote(str(concat_list))} -c copy {shlex.quote(str(source_mp4))}"
        try:
            subprocess.run(
                cmd_copy,
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            # Fallback: re-encode to a uniform source
            cmd_encode = (
                f"ffmpeg -y -f concat -safe 0 -i {shlex.quote(str(concat_list))} "
                f"-c:v libx264 -preset veryfast -c:a aac {shlex.quote(str(source_mp4))}"
            )
            try:
                subprocess.run(
                    cmd_encode,
                    shell=True,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except subprocess.CalledProcessError as e:
                return False, None, f"Failed to build source.mp4: {e}"

    # 3) Ensure ffmpeg HLS process running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except Exception:
            pid = -1
        if pid > 0 and _is_process_alive(pid):
            return True, str(playlist), None
        # stale pid file: remove
        try:
            pid_file.unlink(missing_ok=True)  # type: ignore[arg-type]
        except Exception:
            pass

    # Start process
    seg_pattern = out_dir / "seg_%05d.ts"
    cmd_hls = (
        f"ffmpeg -loglevel warning -nostdin -re -stream_loop -1 -i {shlex.quote(str(source_mp4))} "
        f"-c:v libx264 -preset veryfast -g 48 -sc_threshold 0 -c:a aac -ar 44100 -b:a 128k "
        f"-f hls -hls_time 4 -hls_list_size 6 -hls_flags delete_segments+append_list+independent_segments "
        f"-hls_segment_filename {shlex.quote(str(seg_pattern))} {shlex.quote(str(playlist))}"
    )
    try:
        proc = subprocess.Popen(  # noqa: S603
            cmd_hls,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid,  # allow killing the whole group later
        )
        pid_file.write_text(str(proc.pid))
        # Give it a moment to start writing
        time.sleep(0.5)
        return True, str(playlist), None
    except Exception as e:
        return False, None, f"Failed to start ffmpeg: {e}"


# Simple rotating counter to avoid always sampling the very first frame
_predict_skip_counter = 0


def _next_skip_count() -> int:
    global _predict_skip_counter
    _predict_skip_counter = (_predict_skip_counter + 1) % 60  # cycle 0..59
    base = int(os.getenv("DEMO_PREDICT_SKIP_BASE", "5"))
    # Skip between base..base+counter, bounded to a reasonable max
    return min(base + _predict_skip_counter, 90)


class HealthcheckView(APIView):
    """Health endpoint: verifica modelo, DB e Redis.

    - Modelo baixado: checa existência e tamanho do checkpoint e evita LFS pointer
    - DB OK: abre um cursor e executa um SELECT 1
    - Redis OK: ping no broker configurado (CELERY_BROKER_URL)
    """

    def get(self, request, *args, **kwargs):
        # 1) Modelo
        checkpoint_path = resolve_checkpoint_path()

        model_exists = checkpoint_path.exists() and checkpoint_path.is_file()
        model_size = 0
        if model_exists:
            try:
                model_size = checkpoint_path.stat().st_size
            except Exception:
                model_size = 0
        model_ok = bool(
            model_exists
            and (model_size >= 1024 * 1024)
            and not looks_like_lfs_pointer(checkpoint_path)
        )

        # DB
        db_ok = False
        try:
            with connections["default"].cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            db_ok = True
        except Exception:
            pass

        # Redis broker
        redis_ok = False
        redis_url = getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")
        try:
            r = redis.from_url(redis_url)
            if r.ping():
                redis_ok = True
        except Exception:
            pass

        all_ok = model_ok and db_ok and redis_ok
        payload = {
            "status": "ok" if all_ok else "degraded",
            "model": {
                "ok": model_ok,
                "exists": model_exists,
                "size": model_size,
            },
            "database": {"ok": db_ok},
            "redis": {"ok": redis_ok},
        }
        return Response(
            payload,
            status=(
                status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
            ),
        )


class HlsLoopInfoView(APIView):
    """Return the HLS live loop URL and ensure the stream is running."""

    def get(self, request, *args, **kwargs):
        ok, playlist_path, err = _ensure_hls_live_loop()
        if not ok or not playlist_path:
            return Response({"ok": False, "error": err or "unknown"}, status=503)
        # Build public URL under MEDIA_URL
        rel = Path(playlist_path).relative_to(Path(settings.MEDIA_ROOT)).as_posix()
        hls_url = request.build_absolute_uri(
            (str(settings.MEDIA_URL).rstrip("/") + "/" + rel)
        )
        return Response({"ok": True, "hls_url": hls_url})


## Removed MJPEG and MP4 demo endpoints to simplify


class HlsPredictView(APIView):
    """Return a snapshot prediction for the demo HLS loop source (from media files)."""

    def get(self, request, *args, **kwargs):
        from core.flood_camera_monitoring.adapters.gateways.opencv_stream_adapter import (
            OpenCVVideoStream,
        )
        from core.flood_camera_monitoring.application.dto.snapshot_request import (
            SnapshotDetectRequest,
        )
        from core.flood_camera_monitoring.application.use_cases.detect_flood_snapshot_from_stream import (
            DetectFloodSnapshotFromStream,
        )
        from core.flood_camera_monitoring.infra.torch_flood_classifier import (
            build_default_classifier,
        )

        # Use the same source as HLS (loop of media files)
        loop_url = _media_loop_url()
        if not loop_url:
            raise Http404("No .mp4 files found in MEDIA_ROOT")

        clf = build_default_classifier()
        stream = OpenCVVideoStream(loop_url)
        # Advance a few frames to avoid sampling always the very first frame
        try:
            to_skip = _next_skip_count()
            for _ in range(max(0, to_skip)):
                _ = stream.grab()
                time.sleep(0.005)
        except Exception:
            pass
        service = DetectFloodSnapshotFromStream(classifier=clf, stream=stream)
        try:
            res = service.execute(
                SnapshotDetectRequest(
                    timeout_seconds=float(request.query_params.get("timeout", 5.0)),
                    meta={
                        "skipped_frames": int(to_skip) if "to_skip" in locals() else 0,
                        "source": loop_url,
                        "model_fallback": bool(getattr(clf, "_fallback", False)),
                        "checkpoint": str(getattr(clf, "checkpoint_path", "")),
                    },
                )
            )
        except TimeoutError:
            return Response({"detail": "Could not capture frame"}, status=504)

        return Response(build_prediction_payload(res))
