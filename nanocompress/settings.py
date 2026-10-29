import re
from dataclasses import dataclass
from typing import Optional

RESOLUTIONS = (144, 160, 180, 216, 240, 288, 320, 360, 480, 540, 720)
ENCODERS = ("hevc", "h264")
QUALITIES = ("small", "balanced", "quality")
PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)
DENOISE_LEVELS = ("off", "light", "medium", "strong")

QUALITY_CRF = {
    "hevc": {"quality": 24, "balanced": 28, "small": 32},
    "h264": {"quality": 21, "balanced": 25, "small": 29},
}

_AUDIO_BITRATE_RE = re.compile(r"^\d+[kK]?$")


@dataclass(frozen=True)
class Options:
    resolution: int = 240
    quality: str = "balanced"
    crf: Optional[int] = None
    encoder: str = "hevc"
    preset: str = "slow"
    fps: Optional[int] = None
    audio_bitrate: str = "64k"
    denoise: str = "off"
    ten_bit: bool = False
    tonemap: bool = False
    recursive: bool = False
    overwrite: bool = False
    dry_run: bool = False


def resolve_crf(options: Options) -> int:
    if options.crf is not None:
        return options.crf
    return QUALITY_CRF[options.encoder][options.quality]


def validate_options(options: Options) -> None:
    if options.resolution not in RESOLUTIONS:
        raise ValueError(
            f"resolution must be one of {', '.join(str(r) for r in RESOLUTIONS)}"
        )
    if options.quality not in QUALITIES:
        raise ValueError(f"quality must be one of {', '.join(QUALITIES)}")
    if options.encoder not in ENCODERS:
        raise ValueError(f"encoder must be one of {', '.join(ENCODERS)}")
    if options.preset not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESETS)}")
    if options.denoise not in DENOISE_LEVELS:
        raise ValueError(f"denoise must be one of {', '.join(DENOISE_LEVELS)}")
    if options.crf is not None and not 0 <= options.crf <= 51:
        raise ValueError("crf must be between 0 and 51")
    if options.fps is not None and options.fps <= 0:
        raise ValueError("fps must be greater than zero")
    if options.encoder == "h264" and options.ten_bit:
        raise ValueError("10-bit H.264 is not supported; use the hevc encoder")
    if not _AUDIO_BITRATE_RE.match(options.audio_bitrate):
        raise ValueError("audio bitrate must look like 64k or 96000")
