"""Tipos e casos de uso simples para predição de imagens e streams.

Este módulo é deliberadamente independente de Django, OpenCV e PyTorch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import time
from typing import Any, Generator, Mapping, Protocol, TypeAlias


ImageInput: TypeAlias = bytes | str | Path


class FloodSeverity(Enum):
    NORMAL = "normal"
    MEDIUM = "medium"
    FLOODED = "flooded"


@dataclass(frozen=True)
class FloodProbabilities:
    normal: float
    flooded: float
    medium: float


@dataclass(frozen=True)
class PredictionResult:
    is_flooded: bool
    severity: FloodSeverity
    confidence: float
    probabilities: FloodProbabilities
    meta: Mapping[str, Any] = field(default_factory=dict)

    @property
    def normal(self) -> float:
        return float(self.probabilities.normal)

    @property
    def medium(self) -> float:
        return float(self.probabilities.medium)


# Resultado do classificador e resultado público agora compartilham um tipo.
FloodAssessment = PredictionResult
PredictResponse = PredictionResult


class FloodClassifier(Protocol):
    def predict(self, image: ImageInput) -> PredictionResult: ...


class VideoStream(Protocol):
    def grab(self) -> ImageInput | None: ...
    def is_open(self) -> bool: ...
    def close(self) -> None: ...


def _result(prediction: PredictionResult, meta: Mapping[str, Any]) -> PredictionResult:
    return PredictionResult(
        is_flooded=prediction.is_flooded,
        severity=prediction.severity,
        confidence=prediction.confidence,
        probabilities=prediction.probabilities,
        meta=meta,
    )


def predict_stream(
    *,
    classifier: FloodClassifier,
    stream: VideoStream,
    interval_seconds: float = 5.0,
    max_iterations: int | None = None,
    meta: Mapping[str, Any] | None = None,
) -> Generator[PredictionResult, None, None]:
    """Yield predictions while guaranteeing that the stream is closed."""
    iterations = 0
    metadata = dict(meta or {})
    try:
        while stream.is_open():
            if max_iterations is not None and iterations >= max_iterations:
                break
            frame = stream.grab()
            if frame is not None:
                prediction = classifier.predict(frame)
                yield _result(prediction, {**metadata, "iteration": iterations})
                iterations += 1
            time.sleep(max(0.0, interval_seconds))
    finally:
        stream.close()


def predict_snapshot(
    *,
    classifier: FloodClassifier,
    stream: VideoStream,
    timeout_seconds: float = 5.0,
    meta: Mapping[str, Any] | None = None,
) -> PredictionResult:
    """Return the first available prediction before the timeout."""
    deadline = time.monotonic() + float(timeout_seconds)
    try:
        while stream.is_open() and time.monotonic() < deadline:
            frame = stream.grab()
            if frame is not None:
                return _result(classifier.predict(frame), dict(meta or {}))
            time.sleep(0.05)
    finally:
        stream.close()
    raise TimeoutError("Could not capture frame before timeout")
