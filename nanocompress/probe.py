import json
import subprocess
from dataclasses import dataclass, replace

TEXT_SUBTITLE_CODECS = frozenset(
    {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text"}
)

_HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})
_SDR_TRANSFERS = frozenset({"bt709", "smpte170m", "bt470bg", ""})
_DOLBY_VISION_TAGS = frozenset({"dvh1", "dvhe", "dvav", "dva1"})
_DOLBY_VISION_SIDE_DATA = "DOVI configuration record"


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
    color_space: str = ""
    master_display: str = ""
    max_cll: str = ""
    avg_frame_rate: str = ""
    is_dolby_vision: bool = False


def is_hdr_color(transfer, primaries):
    if transfer in _HDR_TRANSFERS:
        return True
    return primaries == "bt2020" and transfer not in _SDR_TRANSFERS


def is_dolby_vision_stream(stream):
    if (stream.get("codec_tag_string", "") or "") in _DOLBY_VISION_TAGS:
        return True
    for entry in stream.get("side_data_list", []) or []:
        if entry.get("side_data_type", "") == _DOLBY_VISION_SIDE_DATA:
            return True
    return False


def is_interlaced_field_order(field_order):
    if not field_order:
        return False
    return field_order not in ("progressive", "unknown")


def parse_rotation(stream):
    for entry in stream.get("side_data_list", []) or []:
        if "rotation" in entry:
            try:
                return int(round(float(entry["rotation"]))) % 360
            except (TypeError, ValueError):
                break
    tags = stream.get("tags", {}) or {}
    if "rotate" in tags:
        try:
            return int(round(float(tags["rotate"]))) % 360
        except (TypeError, ValueError):
            return 0
    return 0


def _fraction(value):
    numerator, denominator = str(value).split("/", 1)
    numerator_f = float(numerator)
    denominator_f = float(denominator)
    if denominator_f == 0:
        raise ValueError("zero denominator")
    return numerator_f / denominator_f


def parse_master_display(side_data):
    required = (
        "green_x", "green_y", "blue_x", "blue_y", "red_x", "red_y",
        "white_point_x", "white_point_y", "min_luminance", "max_luminance",
    )
    if not all(key in side_data for key in required):
        return ""
    try:
        def chroma(key):
            return round(_fraction(side_data[key]) * 50000)

        def luminance(key):
            return round(_fraction(side_data[key]) * 10000)

        return (
            f"G({chroma('green_x')},{chroma('green_y')})"
            f"B({chroma('blue_x')},{chroma('blue_y')})"
            f"R({chroma('red_x')},{chroma('red_y')})"
            f"WP({chroma('white_point_x')},{chroma('white_point_y')})"
            f"L({luminance('max_luminance')},{luminance('min_luminance')})"
        )
    except (TypeError, ValueError, ZeroDivisionError):
        return ""


def parse_max_cll(side_data):
    if "max_content" not in side_data or "max_average" not in side_data:
        return ""
    try:
        return f"{int(side_data['max_content'])},{int(side_data['max_average'])}"
    except (TypeError, ValueError):
        return ""


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
        color_space=video.get("color_space", "") or "",
        avg_frame_rate=video.get("avg_frame_rate") or video.get("r_frame_rate") or "",
        is_dolby_vision=is_dolby_vision_stream(video),
    )


def _read_hdr_side_data(path):
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_frames",
                "-read_intervals",
                "%+#1",
                "-show_entries",
                "frame=side_data_list",
                "-of",
                "json",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return "", ""

    frames = data.get("frames", []) or []
    if not frames:
        return "", ""
    master_display = ""
    max_cll = ""
    for entry in frames[0].get("side_data_list", []) or []:
        kind = entry.get("side_data_type", "")
        if kind == "Mastering display metadata" and not master_display:
            master_display = parse_master_display(entry)
        elif kind == "Content light level metadata" and not max_cll:
            max_cll = parse_max_cll(entry)
    return master_display, max_cll


def probe(path):
    try:
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
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip() or "ffprobe could not read the file"
        raise RuntimeError(f"could not probe {path}: {detail}") from exc

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"could not parse ffprobe output for {path}: {exc}") from exc

    info = parse_media_info(data)
    if info.is_hdr:
        master_display, max_cll = _read_hdr_side_data(path)
        info = replace(info, master_display=master_display, max_cll=max_cll)
    return info
