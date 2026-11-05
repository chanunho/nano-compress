from dataclasses import dataclass
from typing import Optional

SPEEDS = ("fast", "balanced", "smallest")
PROFILES = ("send", "discord", "email", "storage", "custom")
CODECS = ("h264", "hevc")

DEFAULT_AUDIO_BITRATE = "64k"

_PROFILE_DEFAULTS = {
    "send": ("fast", 720, "h264", None),
    "discord": ("fast", 480, "h264", 10 * 1024 * 1024),
    "email": ("fast", 540, "h264", 25 * 1024 * 1024),
    "storage": ("balanced", 480, "hevc", None),
    "custom": ("fast", 720, "h264", None),
}


@dataclass(frozen=True)
class Profile:
    name: str
    speed: str
    resolution: int
    codec: str
    target_bytes: Optional[int]
    audio_bitrate: str


def resolve_profile(
    name: str,
    *,
    target_mb: Optional[float] = None,
    speed: Optional[str] = None,
    codec: Optional[str] = None,
) -> Profile:
    if name not in PROFILES:
        raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
    if speed is not None and speed not in SPEEDS:
        raise ValueError(f"speed must be one of {', '.join(SPEEDS)}")
    if codec is not None and codec != "auto" and codec not in CODECS:
        raise ValueError(f"codec must be one of {', '.join(CODECS)} or auto")
    if target_mb is not None and target_mb <= 0:
        raise ValueError("target size must be greater than zero")

    default_speed, resolution, default_codec, target_bytes = _PROFILE_DEFAULTS[name]
    if target_mb is not None:
        target_bytes = int(round(target_mb * 1024 * 1024))
    if name == "custom" and target_bytes is None:
        raise ValueError("custom profile requires a target size")

    return Profile(
        name=name,
        speed=default_speed if speed is None else speed,
        resolution=resolution,
        codec=default_codec if codec is None or codec == "auto" else codec,
        target_bytes=target_bytes,
        audio_bitrate=DEFAULT_AUDIO_BITRATE,
    )
