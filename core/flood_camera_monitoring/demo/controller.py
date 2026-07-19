from __future__ import annotations

import logging
import re
import shutil
import signal
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from core.flood_camera_monitoring.demo.manifest import (
    ALLOWED_STATES,
    DemoPhase,
    DemoScenario,
    scenario_as_dict,
)


SEGMENT_RE = re.compile(r"^seg_(\d+)\.ts$")


class DemoStreamError(RuntimeError):
    pass


class DemoStreamController:
    """Owns normalized fixtures and the long-running FFmpeg HLS process."""

    def __init__(
        self,
        scenario: DemoScenario,
        work_dir: str | Path,
        *,
        public_hls_url: str,
        internal_base_url: str,
        source_type: str = "scenario",
    ) -> None:
        self.scenario = scenario
        self.work_dir = Path(work_dir)
        self.normalized_dir = self.work_dir / "normalized"
        self.hls_dir = self.work_dir / "hls"
        self.public_hls_url = public_hls_url
        self.internal_base_url = internal_base_url.rstrip("/")
        self.source_type = source_type
        self.logger = logging.getLogger(__name__)
        self._lock = threading.RLock()
        self._process: subprocess.Popen[bytes] | None = None
        self._log_handle = None
        self._normalized: dict[DemoPhase, Path] = {}
        self.state = "auto"
        self.session_id = ""

    def initialize(self) -> dict[str, Any]:
        self._require_binary("ffmpeg")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)
        self.hls_dir.mkdir(parents=True, exist_ok=True)
        for index, phase in enumerate(self.scenario.phases):
            output = self.normalized_dir / f"phase_{index:03d}.mp4"
            self._normalize_phase(phase, output)
            self._normalized[phase] = output
        return self.set_state("auto")

    @staticmethod
    def _require_binary(name: str) -> None:
        if shutil.which(name) is None:
            raise DemoStreamError(f"Required executable is not available: {name}")

    def _normalize_phase(self, phase: DemoPhase, output: Path) -> None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(phase.file_path),
            "-t",
            str(phase.duration_seconds),
            "-an",
            "-vf",
            "scale=1280:720:force_original_aspect_ratio=decrease,"
            "pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=10",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(self.scenario.segment_seconds * 10),
            "-keyint_min",
            str(self.scenario.segment_seconds * 10),
            "-sc_threshold",
            "0",
            str(output),
        ]
        self._run(command, f"Could not normalize phase '{phase.name}'")

    @staticmethod
    def _run(command: list[str], error_message: str) -> None:
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.decode("utf-8", errors="replace").strip()
            raise DemoStreamError(f"{error_message}: {detail}") from exc

    def set_state(self, state: str) -> dict[str, Any]:
        if state not in ALLOWED_STATES:
            raise DemoStreamError(f"Unsupported demo state: {state}")
        with self._lock:
            phases = self.scenario.phases_for_state(state)
            self._stop_process()
            source = self._build_source(state, phases)
            self._clear_hls()
            self.state = state
            self.session_id = str(uuid.uuid4())
            self._start_hls(source)
            return self.snapshot()

    def _build_source(self, state: str, phases: tuple[DemoPhase, ...]) -> Path:
        concat_file = self.work_dir / f"concat_{state}.txt"
        concat_file.write_text(
            "".join(f"file '{self._normalized[phase].as_posix()}'\n" for phase in phases),
            encoding="utf-8",
        )
        source = self.work_dir / f"source_{state}.mp4"
        self._run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(source),
            ],
            f"Could not build source for state '{state}'",
        )
        return source

    def _clear_hls(self) -> None:
        self.hls_dir.mkdir(parents=True, exist_ok=True)
        for path in self.hls_dir.iterdir():
            if path.is_file():
                path.unlink()

    def _start_hls(self, source: Path) -> None:
        playlist = self.hls_dir / "playlist.m3u8"
        segment_pattern = self.hls_dir / "seg_%09d.ts"
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostdin",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-c:v",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            str(self.scenario.segment_seconds),
            "-hls_list_size",
            "8",
            "-hls_flags",
            "delete_segments+append_list+independent_segments+program_date_time",
            "-hls_segment_filename",
            str(segment_pattern),
            str(playlist),
        ]
        self._log_handle = (self.work_dir / "ffmpeg.log").open("ab")
        try:
            self._process = subprocess.Popen(
                command,
                stdout=self._log_handle,
                stderr=self._log_handle,
                start_new_session=True,
            )
        except Exception:
            self._log_handle.close()
            self._log_handle = None
            raise

    def _stop_process(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            try:
                process.send_signal(signal.SIGTERM)
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None

    def close(self) -> None:
        with self._lock:
            self._stop_process()

    def _latest_segment(self) -> dict[str, Any] | None:
        found: list[tuple[int, Path]] = []
        for path in self.hls_dir.glob("seg_*.ts"):
            match = SEGMENT_RE.match(path.name)
            if match:
                found.append((int(match.group(1)), path))
        found.sort(key=lambda item: item[0])
        if not found:
            return None
        sequence, path = found[-2] if len(found) > 1 else found[-1]
        phase = self.scenario.phase_for_sequence(self.state, sequence)
        return {
            "sequence": sequence,
            "phase": phase.name,
            "expected_state": phase.label,
            "internal_url": f"{self.internal_base_url}/hls/{path.name}",
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            process_ok = self._process is not None and self._process.poll() is None
            playlist_ok = (self.hls_dir / "playlist.m3u8").is_file()
            process_failed = self._process is not None and self._process.poll() is not None
            if process_ok and playlist_ok:
                stream_status = "ready"
            elif process_failed:
                stream_status = "error"
            else:
                stream_status = "starting"
            latest = self._latest_segment()
            return {
                "ok": bool(process_ok),
                "status": stream_status,
                "session_id": self.session_id,
                "demo_state": self.state,
                "available_states": list(self.scenario.available_states),
                "scenario": scenario_as_dict(self.scenario),
                "source": {"type": self.source_type, "status": "resolved"},
                "current_phase": latest["phase"] if latest else None,
                "hls_url": self.public_hls_url,
                "segment": latest,
            }
