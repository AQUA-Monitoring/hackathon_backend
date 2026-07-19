"""Inspeção estática do artefato de inferência.

Não importa Torch, não carrega o checkpoint e não realiza downloads.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

from core.flood_camera_monitoring.infra.utils import (
    looks_like_lfs_pointer,
    resolve_checkpoint_path,
)


@dataclass(frozen=True)
class ModelArtifactInfo:
    available: bool
    path: Path
    version: str | None
    error_code: str | None


def inspect_model_artifact() -> ModelArtifactInfo:
    path = resolve_checkpoint_path()
    try:
        if not path.is_file():
            return ModelArtifactInfo(False, path, None, "MODEL_MISSING")
        stat = path.stat()
        if stat.st_size < 1024 * 1024 or looks_like_lfs_pointer(path):
            return ModelArtifactInfo(False, path, None, "MODEL_INVALID")
    except OSError:
        return ModelArtifactInfo(False, path, None, "MODEL_UNREADABLE")

    identity = f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}"
    version = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return ModelArtifactInfo(True, path, version, None)
