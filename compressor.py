#!/usr/bin/env python3
import argparse
import os
import subprocess
import sys


RESOLUTIONS = ["144", "160", "180", "216", "240", "288", "320", "360", "480", "540", "720"]


def run_cmd(cmd):
    print(f"Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"Command failed with return code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main():
    parser = argparse.ArgumentParser(
        description="NanoCompress - Minimal-size video compression pipeline for universal playback",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("input", help="Input video file (e.g., movie.mp4)")
    parser.add_argument("output", help="Output video file (e.g., movie_compressed.mp4)")
    parser.add_argument(
        "-r",
        "--resolution",
        choices=RESOLUTIONS,
        default="240",
        help="Target height in pixels. Default: 240\nOptions: " + ", ".join(RESOLUTIONS),
    )
    parser.add_argument(
        "-c",
        "--crf",
        type=int,
        default=28,
        help="Constant Rate Factor (18 = visually lossless/larger, 51 = smallest/worst). Default: 28",
    )
    parser.add_argument(
        "-p",
        "--preset",
        default="medium",
        choices=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
        help="Encoding speed vs compression efficiency. Slower = smaller file. Default: medium",
    )
    parser.add_argument(
        "-e",
        "--encoder",
        default="x264",
        choices=["x264", "x265"],
        help="x264 = maximum compatibility (phones/computers). x265 = smaller but less compatible. Default: x264",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="Change framerate (e.g., 24). Leave empty to keep original.",
    )
    parser.add_argument(
        "--audio-bitrate",
        type=str,
        default="64k",
        help="Audio bitrate (e.g., 48k, 64k, 96k). Lower = smaller. Default: 64k",
    )

    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.crf < 18 or args.crf > 51:
        print("CRF should be between 18 and 51", file=sys.stderr)
        sys.exit(1)

    vf_filters = []
    vf_filters.append(f"scale=-2:{args.resolution}:flags=lanczos")
    if args.fps:
        vf_filters.append(f"fps={args.fps}")
    vf = ",".join(vf_filters)

    if args.encoder == "x264":
        vcodec = "libx264"
        acodec = "aac"
        pix_fmt = "yuv420p"
    else:
        vcodec = "libx265"
        acodec = "aac"
        pix_fmt = "yuv420p"

    print(f"Input: {args.input}", flush=True)
    print(f"Resolution: {args.resolution}p | Encoder: {vcodec} | CRF: {args.crf} | Preset: {args.preset}", flush=True)
    print(f"Video filter: {vf}", flush=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        args.input,
        "-vf",
        vf,
        "-c:v",
        vcodec,
        "-crf",
        str(args.crf),
        "-preset",
        args.preset,
        "-pix_fmt",
        pix_fmt,
        "-c:a",
        acodec,
        "-b:a",
        args.audio_bitrate,
        "-movflags",
        "+faststart",
        args.output,
    ]

    run_cmd(cmd)
    print(f"\nDone! {args.output} is ready to play on most phones and computers.", flush=True)


if __name__ == "__main__":
    main()
