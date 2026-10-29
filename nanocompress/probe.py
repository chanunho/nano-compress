import json
import subprocess
from dataclasses import dataclass

TEXT_SUBTITLE_CODECS = frozenset(
    {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}
)

_HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
_SDR_TRANSFERS = frozenset({"bt709", "smpte170m", "bt470bg", ""})


@dataclass(frozen=True)
class Subtitle:
    index: int
    codec: str


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    width: int
    height: int
    video_codec: str
    sample_aspect_ratio: str
    rotation: int
    color_transfer: str
    color_primaries: str
    is_hdr: bool
    is_interlaced: bool
    audio_tracks: int
    subtitles: tuple


def is_hdr_color(transfer, primaries):
    if transfer in _HDR_TRANSFERS:
        return True
    return primaries == "bt2020" and transfer not in _SDR_TRANSFERS


def is_interlaced_field_order(field_order):
    if not field_order:
        return False
    return field_order not in ("progressive", "unknown")


def parse_rotation(stream):
    for entry in stream.get("side_data_list", []) or []:
        if "rotation" in entry:
            return int(round(float(entry["rotation"]))) % 360
    tags = stream.get("tags", {}) or {}
    if "rotate" in tags:
        try:
            return int(round(float(tags["rotate"]))) % 360
        except (TypeError, ValueError):
            return 0
    return 0


def _parse_duration(data):
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


def parse_media_info(data):
    streams = data.get("streams", []) or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError("input has no video stream")

    subtitles = tuple(
        Subtitle(index=stream.get("index", position), codec=stream.get("codec_name", ""))
        for position, stream in enumerate(streams)
        if stream.get("codec_type") == "subtitle"
    )
    transfer = video.get("color_transfer", "") or ""
    primaries = video.get("color_primaries", "") or ""

    return MediaInfo(
        duration=_parse_duration(data),
        width=int(video.get("width", 0) or 0),
        height=int(video.get("height", 0) or 0),
        video_codec=video.get("codec_name", ""),
        sample_aspect_ratio=video.get("sample_aspect_ratio", "") or "",
        rotation=parse_rotation(video),
        color_transfer=transfer,
        color_primaries=primaries,
        is_hdr=is_hdr_color(transfer, primaries),
        is_interlaced=is_interlaced_field_order(video.get("field_order", "")),
        audio_tracks=sum(1 for s in streams if s.get("codec_type") == "audio"),
        subtitles=subtitles,
    )


def probe(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return parse_media_info(json.loads(result.stdout))
