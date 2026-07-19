import logging
from typing import Any, Callable, Optional

from core.sync.auth import login
from core.sync.client import fetch_all
from core.sync.registry import registry
from core.sync.syncers import (
    sync_addressing,
    sync_cameras,
    sync_documents,
    sync_flood_points,
    sync_forecasts,
    sync_images,
    sync_occurrences,
    sync_posts,
    sync_users,
    sync_weather,
)

logger = logging.getLogger(__name__)


def _register_entities():
    registry.register(
        key="images",
        endpoint="/api/upload/images/",
        model=None,
        sync_func=sync_images,
        dependencies=[],
        description="Imagens enviadas ao sistema",
    )
    registry.register(
        key="documents",
        endpoint="/api/upload/documents/",
        model=None,
        sync_func=sync_documents,
        dependencies=[],
        description="Documentos enviados ao sistema",
    )
    registry.register(
        key="addressing",
        endpoint="/api/addressing/regions-neighborhoods/",
        model=None,
        sync_func=sync_addressing,
        dependencies=[],
        description="Cidades, regiões e bairros",
    )
    registry.register(
        key="users",
        endpoint="/api/users/",
        model=None,
        sync_func=sync_users,
        dependencies=["images"],
        description="Usuários do sistema",
    )
    registry.register(
        key="cameras",
        endpoint="/api/flood_monitoring/cameras/",
        model=None,
        sync_func=sync_cameras,
        dependencies=["addressing"],
        description="Câmeras de monitoramento",
    )
    registry.register(
        key="occurrences",
        endpoint="/api/occurrences/occurrences/",
        model=None,
        sync_func=sync_occurrences,
        dependencies=[],
        description="Ocorrências (alertas)",
    )
    registry.register(
        key="posts",
        endpoint="/api/blog/",
        model=None,
        sync_func=sync_posts,
        dependencies=["images"],
        description="Posts do blog",
    )
    registry.register(
        key="weather",
        endpoint="/api/weather/weather",
        model=None,
        sync_func=sync_weather,
        dependencies=["occurrences"],
        description="Dados climáticos",
    )
    registry.register(
        key="forecasts",
        endpoint="/api/forecast/foresee/",
        model=None,
        sync_func=sync_forecasts,
        dependencies=[],
        description="Previsões de enchente",
    )
    registry.register(
        key="flood_points",
        endpoint="/api/floods_point/registering/",
        model=None,
        sync_func=sync_flood_points,
        dependencies=["addressing"],
        description="Pontos de alagamento",
    )


def list_entities() -> str:
    _register_entities()
    lines = []
    lines.append(f"{'Chave':<20} {'Dependências':<30} {'Descrição':<40}")
    lines.append("-" * 90)
    for entity in registry.list():
        deps = ", ".join(entity.dependencies) if entity.dependencies else "(nenhuma)"
        lines.append(f"{entity.key:<20} {deps:<30} {entity.description:<40}")
    return "\n".join(lines)


def sync_all(
    entity_keys: list[str] | None = None,
    page_size: int = 100,
    dry_run: bool = False,
    progress_callback: Optional[Callable[[str, str], Any]] = None,
) -> dict[str, dict]:
    _register_entities()

    ordered = registry.resolve_order(entity_keys)
    results: dict[str, dict] = {}

    token = None
    if not dry_run:
        if progress_callback:
            progress_callback("autenticacao", "Autenticando na API remota...")
        token = login()

    for entity in ordered:
        if progress_callback:
            progress_callback(
                entity.key,
                f"Coletando dados de {entity.key} ({entity.description})...",
            )

        if dry_run:
            results[entity.key] = {
                "status": "dry_run",
                "endpoint": entity.endpoint,
                "created": 0,
                "updated": 0,
            }
            continue

        try:
            data = fetch_all(entity.endpoint, token, page_size=page_size)

            if progress_callback:
                progress_callback(
                    entity.key,
                    f"Sincronizando {len(data) if isinstance(data, list) else 1} registro(s) de {entity.key}...",
                )

            created, updated = entity.sync_func(data, token)
            results[entity.key] = {
                "status": "ok",
                "endpoint": entity.endpoint,
                "created": created,
                "updated": updated,
            }
        except Exception as e:
            logger.exception("Erro ao sincronizar %s", entity.key)
            results[entity.key] = {
                "status": "error",
                "endpoint": entity.endpoint,
                "error": str(e),
            }

    return results
