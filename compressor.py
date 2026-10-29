#!/usr/bin/env python3
import argparse
import sys

from nanocompress.jobs import plan_jobs
from nanocompress.runner import format_summary, run_job
from nanocompress.settings import (
    DENOISE_LEVELS,
    ENCODERS,
    PRESETS,
    QUALITIES,
    RESOLUTIONS,
    Options,
    validate_options,
)

VERSION = "NanoCompress 2.0"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="compressor.py",
        description=(
            "Compress video to the smallest practical MP4 at a chosen "
            "resolution, playable by default on modern phones and computers."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("input", help="input video file, or a folder of videos")
    parser.add_argument(
        "output",
        nargs="?",
        help="output file (file mode) or output folder (folder mode)",
    )
    parser.add_argument(
        "-r",
        "--resolution",
        type=int,
        choices=RESOLUTIONS,
        default=240,
        help="target height in pixels; width is computed from the display aspect ratio",
    )
    parser.add_argument(
        "-q",
        "--quality",
        choices=QUALITIES,
        default="balanced",
        help="named quality level",
    )
    parser.add_argument(
        "-c",
        "--crf",
        type=int,
        default=None,
        help="raw CRF override (0-51); lower is better quality and larger",
    )
    parser.add_argument(
        "-e",
        "--encoder",
        choices=ENCODERS,
        default="hevc",
        help="hevc is smaller and plays on modern devices; h264 is the compatibility fallback",
    )
    parser.add_argument(
        "-p",
        "--preset",
        choices=PRESETS,
        default="slow",
        help="encoder speed/efficiency preset; slower is smaller",
    )
    parser.add_argument("--fps", type=int, default=None, help="optional framerate override")
    parser.add_argument(
        "--audio-bitrate",
        default="64k",
        help="AAC bitrate applied to each audio track",
    )
    parser.add_argument(
        "--denoise",
        choices=DENOISE_LEVELS,
        default="off",
        help="optional denoise before scaling",
    )
    parser.add_argument(
        "--10bit",
        dest="ten_bit",
        action="store_true",
        help="encode 10-bit (better gradients; hevc only)",
    )
    parser.add_argument(
        "--tonemap",
        action="store_true",
        help="convert HDR sources to SDR BT.709 instead of preserving HDR",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="folder mode: also process subfolders",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="re-encode outputs that already exist",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print planned commands without encoding",
    )
    parser.add_argument("--version", action="version", version=VERSION)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    options = Options(
        resolution=args.resolution,
        quality=args.quality,
        crf=args.crf,
        encoder=args.encoder,
        preset=args.preset,
        fps=args.fps,
        audio_bitrate=args.audio_bitrate,
        denoise=args.denoise,
        ten_bit=args.ten_bit,
        tonemap=args.tonemap,
        recursive=args.recursive,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )

    try:
        validate_options(options)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        jobs = plan_jobs(
            args.input,
            args.output,
            recursive=args.recursive,
            overwrite=args.overwrite,
        )
    except FileNotFoundError:
        parser.error(f"input not found: {args.input}")
    except NotADirectoryError:
        parser.error(f"input is not a directory: {args.input}")
    except ValueError as exc:
        parser.error(str(exc))

    if not jobs:
        print("No video files found.")
        return 0

    results = [run_job(job, options) for job in jobs]
    print()
    print(format_summary(results))
    return 0 if all(result.ok or result.skipped for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
