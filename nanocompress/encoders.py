import re
import subprocess
import sys
from dataclasses import dataclass

_ENCODER_LINE = re.compile(r"^\s*[VAS][A-Z.]{5}\s+(\S+)")

_SOFTWARE_CODECS = {
    "libx264": "h264",
    "libx265": "hevc",
}
_HARDWARE_SUFFIXES = ("nvenc", "qsv", "videotoolbox", "amf", "vaapi")

_HARDWARE_PREFERENCE = {
    "darwin": ("videotoolbox",),
    "linux": ("nvenc", "qsv"),
    "win32": ("nvenc", "qsv", "amf"),
}

_SOFTWARE_FALLBACK = {
    "h264": "libx264",
    "hevc": "libx265",
}


@dataclass(frozen=True)
class Encoder:
    name: str
    codec: str
    hardware: bool


def _classify(name):
    for software_name, codec in _SOFTWARE_CODECS.items():
        if software_name in name:
            return codec, False
    for suffix in _HARDWARE_SUFFIXES:
        if f"_{suffix}" in name:
            return name.split("_", 1)[0], True
    return name, False


def parse_encoders(text):
    encoders = []
    for line in text.splitlines():
        match = _ENCODER_LINE.match(line)
        if match is None:
            continue
        name = match.group(1)
        if name == "=":
            continue
        codec, hardware = _classify(name)
        encoders.append(Encoder(name=name, codec=codec, hardware=hardware))
    return tuple(encoders)


def detect_encoders(runner=subprocess.run):
    result = runner(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    )
    return parse_encoders(result.stdout)


def choose_encoder(
    codec,
    speed,
    available,
    *,
    platform=sys.platform,
    allow_hardware=True,
):
    if speed != "smallest" and allow_hardware:
        for suffix in _HARDWARE_PREFERENCE.get(platform, ()):
            candidate = f"{codec}_{suffix}"
            for encoder in available:
                if encoder.hardware and encoder.name == candidate:
                    return encoder.name

    fallback = _SOFTWARE_FALLBACK.get(codec)
    for encoder in available:
        if encoder.name == fallback and not encoder.hardware:
            return encoder.name
    raise RuntimeError(f"no usable {codec} encoder found")


def encoder_preset(speed, codec):
    if speed == "fast":
        return "veryfast" if codec == "h264" else "fast"
    if speed == "balanced":
        return "medium"
    if speed == "smallest":
        return "slow"
    raise ValueError(f"unknown speed: {speed}")
