from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass

DURATION_TOLERANCE = 1.0
_DECODE_FRACTIONS = (0.0, 0.5, 0.9)
_DECODE_SECONDS = "1"


@dataclass(frozen=True)
class Verification:
    ok: bool
    reasons: tuple[str, ...]
    duration: float
    video_codec: str
    audio_tracks: int


def _duration(data):
    format_duration = (data.get("format", {}) or {}).get("duration")
    if format_duration not in (None, "N/A"):
        try:
            return float(format_duration)
        except (TypeError, ValueError):
            pass
    durations = []
    for stream in data.get("streams", []) or []:
        value = stream.get("duration")
        if value not in (None, "N/A"):
            try:
                durations.append(float(value))
            except (TypeError, ValueError):
                continue
    return max(durations) if durations else 0.0


def _run(runner, args):
    try:
        return runner(args, capture_output=True, text=True, check=False), None
    except OSError as exc:
        return None, str(exc)


def _probe(path, runner):
    args = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        path,
    ]
    result, error = _run(runner, args)
    if error is not None:
        return None, f"ffprobe could not run: {error}"
    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        return None, f"ffprobe failed: {detail or 'nonzero exit'}"
    try:
        return json.loads(result.stdout), None
    except (TypeError, json.JSONDecodeError):
        return None, "could not parse ffprobe output"


def _decode_reasons(path, duration, runner):
    reasons = []
    for fraction in _DECODE_FRACTIONS:
        timestamp = duration * fraction
        args = [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-t",
            _DECODE_SECONDS,
            "-i",
            path,
            "-f",
            "null",
            "-",
        ]
        result, error = _run(runner, args)
        label = f"decode failed at {fraction:.0%}: "
        if error is not None:
            reasons.append(label + error)
        elif result.returncode != 0:
            detail = (result.stderr or "").strip()
            reasons.append(label + (detail or "nonzero exit"))
    return reasons


def verify_output(
    path: str,
    expected_duration: float,
    expected_audio_tracks: int,
    *,
    runner=subprocess.run,
) -> Verification:
    try:
        size = os.path.getsize(path)
    except OSError:
        return Verification(False, ("output file is missing or empty",), 0.0, "", 0)
    if size == 0:
        return Verification(False, ("output file is missing or empty",), 0.0, "", 0)

    data, error = _probe(path, runner)
    if data is None:
        return Verification(False, (error,), 0.0, "", 0)

    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    duration = _duration(data)
    video_codec = (video or {}).get("codec_name", "") or ""
    audio_tracks = sum(1 for s in streams if s.get("codec_type") == "audio")

    reasons = []
    if video is None:
        reasons.append("output has no video stream")
    if abs(duration - expected_duration) > DURATION_TOLERANCE:
        reasons.append(
            f"duration {duration:.2f}s differs from expected {expected_duration:.2f}s"
        )
    if audio_tracks != expected_audio_tracks:
        reasons.append(
            f"audio track count {audio_tracks} differs from expected "
            f"{expected_audio_tracks}"
        )
    if video is not None and duration > 0:
        reasons.extend(_decode_reasons(path, duration, runner))

    return Verification(
        not reasons,
        tuple(reasons),
        duration,
        video_codec,
        audio_tracks,
    )


def needs_h264_fallback(result: Verification) -> bool:
    return not result.ok
