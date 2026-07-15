from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_LABELS = {"normal", "medium", "flooded"}
ALLOWED_STATES = {"auto", "normal", "flooded"}


class DemoManifestError(ValueError):
    """Raised when a demo scenario cannot be safely executed."""


@dataclass(frozen=True)
class DemoPhase:
    name: str
    file_path: Path
    label: str
    duration_seconds: int


@dataclass(frozen=True)
class DemoScenario:
    scenario_id: str
    phases: tuple[DemoPhase, ...]
    segment_seconds: int = 2

    @property
    def available_states(self) -> tuple[str, ...]:
        labels = {phase.label for phase in self.phases}
        return ("auto",) + tuple(
            state for state in ("normal", "flooded") if state in labels
        )

    def phases_for_state(self, state: str) -> tuple[DemoPhase, ...]:
        if state not in ALLOWED_STATES:
            raise DemoManifestError(f"Unsupported demo state: {state}")
        if state == "auto":
            return self.phases
        selected = tuple(phase for phase in self.phases if phase.label == state)
        if not selected:
            raise DemoManifestError(f"Scenario has no phase for state '{state}'")
        return selected

    def phase_for_sequence(self, state: str, sequence: int) -> DemoPhase:
        if sequence < 0:
            raise DemoManifestError("Segment sequence cannot be negative")

        phases = self.phases_for_state(state)
        timeline: list[DemoPhase] = []
        for phase in phases:
            timeline.extend([phase] * (phase.duration_seconds // self.segment_seconds))
        if not timeline:
            raise DemoManifestError("Scenario timeline is empty")
        return timeline[sequence % len(timeline)]


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DemoManifestError(f"'{field}' must be an object")
    return value


def _safe_asset_path(asset_root: Path, raw_path: Any) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise DemoManifestError("Every phase must define a non-empty 'file'")
    if "\n" in raw_path or "\r" in raw_path or "'" in raw_path:
        raise DemoManifestError("Phase file contains unsupported characters")
    root = asset_root.resolve()
    candidate = (root / raw_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise DemoManifestError("Phase file must stay inside the demo assets directory")
    if not candidate.is_file():
        raise DemoManifestError(f"Demo video not found: {raw_path}")
    return candidate


def load_scenario(path: str | Path) -> DemoScenario:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        raise DemoManifestError(f"Scenario manifest not found: {manifest_path}")

    try:
        raw = _require_mapping(
            json.loads(manifest_path.read_text(encoding="utf-8")), "scenario"
        )
    except json.JSONDecodeError as exc:
        raise DemoManifestError(f"Invalid scenario JSON: {exc}") from exc

    scenario_id = raw.get("scenario_id")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise DemoManifestError("'scenario_id' must be a non-empty string")

    segment_seconds = raw.get("segment_seconds", 2)
    if isinstance(segment_seconds, bool) or not isinstance(segment_seconds, int):
        raise DemoManifestError("'segment_seconds' must be an integer")
    if segment_seconds <= 0:
        raise DemoManifestError("'segment_seconds' must be greater than zero")

    raw_phases = raw.get("phases")
    if not isinstance(raw_phases, list) or not raw_phases:
        raise DemoManifestError("'phases' must be a non-empty list")

    phases: list[DemoPhase] = []
    for index, value in enumerate(raw_phases):
        phase = _require_mapping(value, f"phases[{index}]")
        name = phase.get("name")
        label = phase.get("label")
        duration = phase.get("duration_seconds")
        if not isinstance(name, str) or not name.strip():
            raise DemoManifestError(f"phases[{index}].name must be non-empty")
        if label not in ALLOWED_LABELS:
            raise DemoManifestError(
                f"phases[{index}].label must be one of {sorted(ALLOWED_LABELS)}"
            )
        if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
            raise DemoManifestError(
                f"phases[{index}].duration_seconds must be a positive integer"
            )
        if duration % segment_seconds != 0:
            raise DemoManifestError(
                f"phases[{index}].duration_seconds must be divisible by segment_seconds"
            )
        phases.append(
            DemoPhase(
                name=name.strip(),
                file_path=_safe_asset_path(manifest_path.parent, phase.get("file")),
                label=str(label),
                duration_seconds=duration,
            )
        )

    labels = {phase.label for phase in phases}
    if not labels.intersection({"normal", "flooded"}):
        raise DemoManifestError(
            "Scenario must include at least one normal or flooded phase"
        )

    return DemoScenario(
        scenario_id=scenario_id.strip(),
        phases=tuple(phases),
        segment_seconds=segment_seconds,
    )


def scenario_as_dict(scenario: DemoScenario) -> dict[str, Any]:
    return {
        "scenario_id": scenario.scenario_id,
        "segment_seconds": scenario.segment_seconds,
        "available_states": list(scenario.available_states),
        "phases": [
            {
                "name": phase.name,
                "label": phase.label,
                "duration_seconds": phase.duration_seconds,
            }
            for phase in scenario.phases
        ],
    }
