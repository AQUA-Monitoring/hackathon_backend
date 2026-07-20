"""Infraestrutura legada para produzir um loop HLS local com FFmpeg."""

from pathlib import Path
import os
import shlex
import subprocess
import time

from django.conf import settings

def media_loop_url() -> str | None:
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


def ensure_hls_live_loop() -> tuple[bool, str | None, str | None]:
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


def next_skip_count() -> int:
    global _predict_skip_counter
    _predict_skip_counter = (_predict_skip_counter + 1) % 60  # cycle 0..59
    base = int(os.getenv("DEMO_PREDICT_SKIP_BASE", "5"))
    # Skip between base..base+counter, bounded to a reasonable max
    return min(base + _predict_skip_counter, 90)
