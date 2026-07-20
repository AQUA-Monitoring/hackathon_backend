"""Factory for the Torch classifier implementation kept in infrastructure."""

from pathlib import Path
from typing import Union
import os
import logging
from core.flood_camera_monitoring.infra.utils import (
    resolve_checkpoint_path,
    looks_like_lfs_pointer,
)

from core.flood_camera_monitoring.infra.torch_classifier import (
    TorchFloodClassifier as TorchFloodClassifier,
)


def build_default_classifier(
    checkpoint_path: Union[str, Path] | None = None, device: str = "cpu"
) -> TorchFloodClassifier:
    """Create a TorchFloodClassifier ensuring a valid checkpoint exists.

    Resolution order for checkpoint path:
    1) Explicit argument
    2) ENV FLOOD_MODEL_PATH
    3) Default: <this_dir>/machine_model/best_real_model.pth

    If the file is missing or looks like a Git LFS pointer/tiny stub, we
    download the real checkpoint via gdown.
    """

    # Choose path from args, env or default
    if checkpoint_path is None:
        checkpoint_path = resolve_checkpoint_path()
    else:
        checkpoint_path = Path(str(checkpoint_path))

    # Ensure folder exists
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    needs_download = False
    if not checkpoint_path.exists() or checkpoint_path.is_dir():
        needs_download = True
        size = 0
    else:
        try:
            size = checkpoint_path.stat().st_size
        except Exception:
            size = 0
    if looks_like_lfs_pointer(checkpoint_path) or size < 1024 * 1024:
        needs_download = True

    if needs_download:
        # Prefer full URL from env; otherwise, build from Google Drive ID
        url = os.getenv(
            "FLOOD_MODEL_URL",
            None,
        )
        if not url:
            drive_id = os.getenv(
                "FLOOD_MODEL_DRIVE_ID",
            )
            url = f"https://drive.google.com/uc?export=download&id={drive_id}"
        try:
            if checkpoint_path.exists() and checkpoint_path.is_file():
                checkpoint_path.unlink()
        except Exception:
            pass
        # Download model using gdown if available, otherwise fallback to requests
        try:
            try:
                import gdown  # type: ignore

                logging.getLogger(__name__).info("Downloading model via gdown: %s", url)
                gdown.download(url, str(checkpoint_path), quiet=False)
            except Exception:
                import requests

                logging.getLogger(__name__).info("Downloading model via HTTP: %s", url)
                with requests.get(url, stream=True, timeout=60) as r:  # type: ignore
                    r.raise_for_status()
                    with open(checkpoint_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
        except Exception as e:
            logging.getLogger(__name__).error("Failed to download checkpoint: %s", e)

    return TorchFloodClassifier(str(checkpoint_path), device=device)


# Public compatibility name used by the demo evaluator.  Keep one factory so
# demo and real-camera paths resolve the exact same checkpoint and classifier.
get_default_classifier = build_default_classifier
