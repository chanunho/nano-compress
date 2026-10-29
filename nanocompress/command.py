from dataclasses import dataclass

from nanocompress.probe import MediaInfo, TEXT_SUBTITLE_CODECS
from nanocompress.settings import Options, resolve_crf

DENOISE_FILTERS = {
    "off": None,
    "light": "hqdn3d=1.5:1.5:6:6",
    "medium": "hqdn3d=3:3:9:9",
    "strong": "hqdn3d=6:6:12:12",
}

_ENCODER_CODEC = {"hevc": "libx265", "h264": "libx264"}


@dataclass(frozen=True)
class EncodeJob:
    input_path: str
    output_path: str
    media: MediaInfo
    options: Options


@dataclass(frozen=True)
class Command:
    args: tuple
    warnings: tuple


def should_tonemap(media, options):
    return media.is_hdr and (options.tonemap or options.encoder == "h264")


def parse_sar(value):
    if not value:
        return 1.0
    try:
        numerator, denominator = value.split(":", 1)
        numerator_f = float(numerator)
        denominator_f = float(denominator)
    except (AttributeError, TypeError, ValueError):
        return 1.0
    if numerator_f <= 0 or denominator_f <= 0:
        return 1.0
    return numerator_f / denominator_f


def target_width(media, height):
    if media.width <= 0 or media.height <= 0:
        return max(2, 2 * round(height / 2))
    sar = parse_sar(media.sample_aspect_ratio)
    if media.rotation % 180 == 90:
        value = height * media.height / (media.width * sar)
    else:
        value = height * media.width * sar / media.height
    return max(2, 2 * round(value / 2))


def resolve_pix_fmt(media, options):
    if options.ten_bit or (media.is_hdr and not should_tonemap(media, options)):
        return "yuv420p10le"
    return "yuv420p"


def build_filters(media, options):
    parts = []
    if should_tonemap(media, options):
        parts.append(
            "zscale=t=linear:npl=100,format=gbrpf32le,"
            "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,"
            f"format={resolve_pix_fmt(media, options)}"
        )
    if media.is_interlaced:
        parts.append("yadif")
    denoise = DENOISE_FILTERS[options.denoise]
    if denoise:
        parts.append(denoise)
    parts.append(
        f"scale={target_width(media, options.resolution)}:{options.resolution}:flags=lanczos"
    )
    parts.append("setsar=1")
    if options.fps:
        parts.append(f"fps={options.fps}")
    return ",".join(parts)


def build_command(job):
    media = job.media
    options = job.options
    tonemap = should_tonemap(media, options)
    warnings = []

    if options.tonemap and not media.is_hdr:
        warnings.append("Source is SDR; --tonemap has no effect.")
    if tonemap and media.is_hdr and options.encoder == "h264":
        warnings.append(
            "Source is HDR; tone-mapping to SDR because H.264 is not "
            "default-playable as HDR."
        )

    text_subtitles = [
        subtitle
        for subtitle in media.subtitles
        if subtitle.codec in TEXT_SUBTITLE_CODECS
    ]
    for subtitle in media.subtitles:
        if subtitle.codec not in TEXT_SUBTITLE_CODECS:
            warnings.append(
                f"Skipping image-based subtitle stream {subtitle.index} "
                f"({subtitle.codec}); MP4 cannot store it."
            )

    args = [
        "ffmpeg",
        "-y",
        "-i",
        job.input_path,
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
    ]
    for subtitle in text_subtitles:
        args += ["-map", f"0:{subtitle.index}"]
    args += [
        "-map_metadata",
        "0",
        "-map_chapters",
        "0",
        "-vf",
        build_filters(media, options),
        "-c:v",
        _ENCODER_CODEC[options.encoder],
        "-crf",
        str(resolve_crf(options)),
        "-preset",
        options.preset,
        "-pix_fmt",
        resolve_pix_fmt(media, options),
    ]

    if media.is_hdr and not tonemap:
        args += [
            "-color_primaries",
            media.color_primaries or "bt2020",
            "-color_trc",
            media.color_transfer or "smpte2084",
            "-colorspace",
            media.color_space or "bt2020nc",
        ]
        x265_params = []
        if media.master_display:
            x265_params.append(f"master-display={media.master_display}")
        if media.max_cll:
            x265_params.append(f"max-cll={media.max_cll}")
        if options.encoder == "hevc" and x265_params:
            args += ["-x265-params", ":".join(x265_params)]

    if options.encoder == "hevc":
        args += ["-tag:v", "hvc1"]

    args += ["-c:a", "aac", "-b:a", options.audio_bitrate]
    if text_subtitles:
        args += ["-c:s", "mov_text"]
    args += ["-movflags", "+faststart", job.output_path]

    return Command(tuple(args), tuple(warnings))
