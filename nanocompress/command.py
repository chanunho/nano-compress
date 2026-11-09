from dataclasses import dataclass
from typing import Optional, Tuple

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


@dataclass(frozen=True)
class EncodePlan:
    encoder: str
    encoder_preset: str
    resolution: int
    crf: Optional[int]
    video_kbps: Optional[int]
    audio_bitrate: str
    keep_hdr: bool
    keep_metadata: bool
    compatibility: bool
    target_bytes: Optional[int]


@dataclass(frozen=True)
class ProductEncodeJob:
    input_path: str
    output_path: str
    passlog_path: str
    media: MediaInfo
    plan: EncodePlan


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


_HARDWARE_ENCODER_SUFFIXES = ("nvenc", "qsv", "videotoolbox", "amf", "vaapi")


def _is_hardware_encoder(encoder):
    return any(f"_{suffix}" in encoder for suffix in _HARDWARE_ENCODER_SUFFIXES)


def _is_hevc_encoder(encoder):
    return "265" in encoder or encoder.startswith("hevc")


def _product_tonemap(media, plan):
    return media.is_dolby_vision or (media.is_hdr and not plan.keep_hdr)


def _product_pix_fmt(media, plan, tonemap):
    if plan.keep_hdr and media.is_hdr and not media.is_dolby_vision and not tonemap:
        return "yuv420p10le"
    return "yuv420p"


def build_product_filters(media, plan):
    tonemap = _product_tonemap(media, plan)
    pix_fmt = _product_pix_fmt(media, plan, tonemap)
    parts = []
    if tonemap:
        parts.append(
            "zscale=t=linear:npl=100,format=gbrpf32le,"
            "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv,"
            f"format={pix_fmt}"
        )
    if plan.compatibility:
        parts.append("fps=30")
    parts.append(
        f"scale={target_width(media, plan.resolution)}:{plan.resolution}:flags=lanczos"
    )
    parts.append("setsar=1")
    return ",".join(parts)


def _product_subtitles_and_warnings(media):
    text_subtitles = [
        subtitle
        for subtitle in media.subtitles
        if subtitle.codec in TEXT_SUBTITLE_CODECS
    ]
    warnings = []
    if media.is_dolby_vision:
        warnings.append(
            "Source is Dolby Vision; tone-mapping to SDR because Dolby Vision "
            "cannot be preserved."
        )
    for subtitle in media.subtitles:
        if subtitle.codec not in TEXT_SUBTITLE_CODECS:
            warnings.append(
                f"Skipping image-based subtitle stream {subtitle.index} "
                f"({subtitle.codec}); MP4 cannot store it."
            )
    return text_subtitles, warnings


def _product_metadata_args(plan):
    value = "0" if plan.keep_metadata else "-1"
    return ["-map_metadata", value, "-map_chapters", value]


def _product_video_args(media, plan, tonemap):
    args = ["-c:v", plan.encoder]
    if plan.target_bytes is not None and plan.video_kbps is not None:
        args += _product_bitrate_args(plan)
        if not _is_hardware_encoder(plan.encoder):
            args += ["-preset", plan.encoder_preset]
    elif plan.crf is not None:
        args += ["-crf", str(plan.crf), "-preset", plan.encoder_preset]
    elif plan.video_kbps is not None:
        args += _product_bitrate_args(plan)
        if not _is_hardware_encoder(plan.encoder):
            args += ["-preset", plan.encoder_preset]
    else:
        raise ValueError("plan requires crf or video_kbps")

    args += ["-pix_fmt", _product_pix_fmt(media, plan, tonemap)]
    # Keep both two-pass runs on the same frames and preserve source timestamps.
    args += ["-fps_mode", "passthrough"]

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
        if plan.encoder == "libx265" and x265_params:
            args += ["-x265-params", ":".join(x265_params)]

    if _is_hevc_encoder(plan.encoder):
        args += ["-tag:v", "hvc1"]

    return args


def _product_bitrate_args(plan):
    maxrate = max(1, int(plan.video_kbps * 1.2))
    bufsize = plan.video_kbps * 2
    return [
        "-b:v",
        f"{plan.video_kbps}k",
        "-maxrate",
        f"{maxrate}k",
        "-bufsize",
        f"{bufsize}k",
    ]


def _product_output_args(text_subtitles, plan):
    args = ["-c:a", "aac", "-b:a", plan.audio_bitrate]
    if text_subtitles:
        args += ["-c:s", "mov_text"]
    args += ["-movflags", "+faststart"]
    return args


def build_product_commands(job: ProductEncodeJob) -> Tuple[Command, ...]:
    media = job.media
    plan = job.plan
    tonemap = _product_tonemap(media, plan)
    text_subtitles, warnings = _product_subtitles_and_warnings(media)

    prefix = ["ffmpeg", "-y", "-i", job.input_path]
    metadata = _product_metadata_args(plan)
    filters = ["-vf", build_product_filters(media, plan)]
    video = _product_video_args(media, plan, tonemap)
    subtitle_maps = []
    for subtitle in text_subtitles:
        subtitle_maps += ["-map", f"0:{subtitle.index}"]

    if plan.video_kbps is not None and plan.target_bytes is not None:
        if _is_hardware_encoder(plan.encoder):
            raise ValueError(
                "target size mode requires a software encoder; "
                f"{plan.encoder} is hardware"
            )
        passlog = ["-passlogfile", job.passlog_path]
        pass_one = (
            prefix
            + ["-map", "0:v:0"]
            + metadata
            + filters
            + video
            + ["-pass", "1"]
            + passlog
            + ["-an", "-sn", "-f", "null", "-"]
        )
        pass_two = (
            prefix
            + ["-map", "0:v:0", "-map", "0:a?"]
            + subtitle_maps
            + metadata
            + filters
            + video
            + ["-pass", "2"]
            + passlog
            + _product_output_args(text_subtitles, plan)
            + [job.output_path]
        )
        return (
            Command(tuple(pass_one), tuple(warnings)),
            Command(tuple(pass_two), tuple(warnings)),
        )

    args = (
        prefix
        + ["-map", "0:v:0", "-map", "0:a?"]
        + subtitle_maps
        + metadata
        + filters
        + video
        + _product_output_args(text_subtitles, plan)
        + [job.output_path]
    )
    return (Command(tuple(args), tuple(warnings)),)
