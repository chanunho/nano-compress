import os
import subprocess
from dataclasses import dataclass

from nanocompress.command import EncodeJob, build_command, should_tonemap
from nanocompress.jobs import TempOutput
from nanocompress.probe import probe

_UNITS = ("B", "KB", "MB", "GB", "TB")


@dataclass(frozen=True)
class JobResult:
    input_path: str
    output_path: str
    original_size: int
    output_size: int
    ok: bool
    skipped: bool = False
    error: str = ""
    dry_run: bool = False


def human_size(num_bytes):
    if num_bytes < 1024:
        return f"{num_bytes} B"
    value = float(num_bytes)
    for unit in _UNITS[1:]:
        value /= 1024.0
        if value < 1024.0:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} {_UNITS[-1]}"


def _size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _percent_saved(original, output):
    if original <= 0:
        return 0.0
    return (original - output) * 100.0 / original


def format_summary(results):
    lines = ["Summary:"]
    encoded = skipped = failed = planned = 0
    original_total = output_total = 0
    for result in results:
        if result.skipped:
            skipped += 1
            status = "skipped"
        elif result.dry_run:
            planned += 1
            status = "planned"
        elif result.ok:
            encoded += 1
            original_total += result.original_size
            output_total += result.output_size
            status = "ok"
        else:
            failed += 1
            status = "failed"
        line = (
            f"  [{status}] {result.input_path} -> {result.output_path}: "
            f"{human_size(result.original_size)} -> {human_size(result.output_size)}"
        )
        if result.error:
            line += f" ({result.error})"
        lines.append(line)
    lines.append(
        f"Totals: {encoded} encoded, {skipped} skipped, {planned} planned, "
        f"{failed} failed; "
        f"{human_size(original_total)} -> {human_size(output_total)} "
        f"({_percent_saved(original_total, output_total):.1f}% saved)"
    )
    return "\n".join(lines)


def _print_header(job, media):
    print(
        f"\n=== {job.input_path} | {human_size(_size(job.input_path))} | "
        f"{media.duration / 60:.1f} min | {media.width}x{media.height} ===",
        flush=True,
    )


def run_job(job, options):
    if job.skip:
        return JobResult(
            job.input_path,
            job.output_path,
            _size(job.input_path),
            _size(job.output_path),
            True,
            skipped=True,
        )

    media = None
    try:
        media = probe(job.input_path)
        _print_header(job, media)

        if options.dry_run:
            command = build_command(
                EncodeJob(job.input_path, job.output_path, media, options)
            )
            for warning in command.warnings:
                print(f"warning: {warning}", flush=True)
            print(
                f"dry-run: resolution={options.resolution} "
                f"crf={options.crf if options.crf is not None else 'auto'}",
                flush=True,
            )
            print(f"dry-run: {' '.join(command.args)}", flush=True)
            return JobResult(
                job.input_path,
                job.output_path,
                _size(job.input_path),
                0,
                True,
            )

        output_dir = os.path.dirname(os.path.abspath(job.output_path))
        os.makedirs(output_dir, exist_ok=True)

        with TempOutput(job.output_path) as temp_path:
            command = build_command(
                EncodeJob(job.input_path, temp_path, media, options)
            )
            for warning in command.warnings:
                print(f"warning: {warning}", flush=True)
            print(f"running: {' '.join(command.args)}", flush=True)
            returncode = subprocess.run(command.args, check=False).returncode
            if returncode != 0:
                message = f"ffmpeg exited with code {returncode}"
                if should_tonemap(media, options):
                    message += (
                        "; if tone-mapping failed, this FFmpeg build may lack zscale"
                    )
                raise RuntimeError(message)

        original_size = _size(job.input_path)
        output_size = _size(job.output_path)
        print(
            f"done: {human_size(original_size)} -> {human_size(output_size)} "
            f"({_percent_saved(original_size, output_size):.1f}% saved)",
            flush=True,
        )
        return JobResult(
            job.input_path,
            job.output_path,
            original_size,
            output_size,
            True,
        )
    except Exception as exc:
        print(f"error: {exc}", flush=True)
        return JobResult(
            job.input_path,
            job.output_path,
            _size(job.input_path),
            0,
            False,
            error=str(exc),
        )
