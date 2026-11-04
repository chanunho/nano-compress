from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Optional

from nanocompress.command import EncodePlan, ProductEncodeJob, build_product_commands
from nanocompress.encoders import choose_encoder, detect_encoders, encoder_preset
from nanocompress.jobs import TempOutput
from nanocompress.presets import resolve_profile
from nanocompress.probe import probe
from nanocompress.process import Cancelled, Progress, run_with_progress
from nanocompress.target_size import next_bitrate, plan_size, within_cap
from nanocompress.verify import verify_output

PASSLOG_NAME = ".nanocompress-pass"

_MAX_ATTEMPTS = 3
_ALREADY_SMALL_RATIO = 0.98
_SHARING_PROFILES = frozenset({"send", "discord", "email"})
_SOFTWARE_CRF = {"send": 26, "storage": 32}
_DEFAULT_CRF = 26
_HARDWARE_RESOLUTION_KBPS = {720: 1000, 540: 800, 480: 600}
_DEFAULT_HARDWARE_KBPS = 600
_RESOLUTION_STEPS = (720, 540, 480, 360)
_HARDWARE_ENCODER_SUFFIXES = ("nvenc", "qsv", "videotoolbox", "amf", "vaapi")
_SOFTWARE_FALLBACK = {"h264": "libx264", "hevc": "libx265"}


@dataclass(frozen=True)
class CompressRequest:
    input_path: str
    output_path: str
    profile: str = "send"
    target_mb: Optional[float] = None
    speed: Optional[str] = None
    codec: Optional[str] = None
    keep_hdr: bool = False
    keep_metadata: bool = False
    compatibility: bool = False
    overwrite: bool = False
    dry_run: bool = False
    verify: bool = True


@dataclass(frozen=True)
class CompressResult:
    ok: bool
    output_path: str
    original_size: int
    output_size: int
    saved_percent: float
    encoder: str
    warnings: tuple[str, ...]
    error: str = ""
    skipped: bool = False
    already_small: bool = False
    planned_commands: tuple[str, ...] = ()


class _SizeExceeded(Exception):
    def __init__(self, actual_bytes):
        super().__init__(actual_bytes)
        self.actual_bytes = actual_bytes


class _VerificationFailed(Exception):
    def __init__(self, result):
        super().__init__("verification failed")
        self.result = result


def _is_hardware_encoder(name):
    return any(f"_{suffix}" in name for suffix in _HARDWARE_ENCODER_SUFFIXES)


def _encoder_codec(encoder, fallback):
    if "264" in encoder:
        return "h264"
    if "265" in encoder or encoder.startswith("hevc"):
        return "hevc"
    return fallback


def _drop_resolution(height):
    lower = [step for step in _RESOLUTION_STEPS if step < height]
    return max(lower) if lower else _RESOLUTION_STEPS[-1]


def _passlog_path(output_path):
    directory = os.path.dirname(os.path.abspath(output_path))
    return os.path.join(directory, PASSLOG_NAME)


def _cleanup_passlog(passlog_path):
    for candidate in glob.glob(passlog_path + "*"):
        try:
            os.remove(candidate)
        except OSError:
            pass


def _add_warnings(warnings, new_warnings):
    for warning in new_warnings:
        if warning not in warnings:
            warnings.append(warning)


def _file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _saved_percent(original_size, output_size):
    if original_size <= 0:
        return 0.0
    return (original_size - output_size) / original_size * 100.0


def _failure(output_path, original_size, encoder, warnings, error):
    return CompressResult(
        ok=False,
        output_path=output_path,
        original_size=original_size,
        output_size=0,
        saved_percent=0.0,
        encoder=encoder,
        warnings=tuple(warnings),
        error=error,
    )


def _finish(input_path, output_path, original_size, output_size, encoder, warnings):
    if (
        original_size > 0
        and output_size >= original_size * _ALREADY_SMALL_RATIO
    ):
        try:
            os.remove(output_path)
        except OSError:
            pass
        return CompressResult(
            ok=True,
            output_path=input_path,
            original_size=original_size,
            output_size=original_size,
            saved_percent=0.0,
            encoder=encoder,
            warnings=tuple(warnings),
            already_small=True,
        )
    return CompressResult(
        ok=True,
        output_path=output_path,
        original_size=original_size,
        output_size=output_size,
        saved_percent=_saved_percent(original_size, output_size),
        encoder=encoder,
        warnings=tuple(warnings),
    )


def _make_plan(
    encoder,
    profile,
    resolution,
    crf,
    video_kbps,
    target_bytes,
    request,
):
    codec = _encoder_codec(encoder, profile.codec)
    return EncodePlan(
        encoder=encoder,
        encoder_preset=encoder_preset(profile.speed, codec),
        resolution=resolution,
        crf=crf,
        video_kbps=video_kbps,
        audio_bitrate=profile.audio_bitrate,
        keep_hdr=request.keep_hdr,
        keep_metadata=request.keep_metadata,
        compatibility=request.compatibility,
        target_bytes=target_bytes,
    )


def _run_commands(commands, duration_s, runner, progress, cancel):
    two_pass = len(commands) == 2
    for index, command in enumerate(commands):
        callback = progress
        if progress is not None and two_pass:
            start = 0.0 if index == 0 else 50.0

            def callback(frame, _start=start):
                progress(
                    Progress(
                        percent=_start + frame.percent * 0.5,
                        seconds=frame.seconds,
                        speed=frame.speed,
                    )
                )

        options = {"progress": callback}
        if cancel is not None:
            options["cancel"] = cancel
        runner(command.args, duration_s, **options)


def _encode_attempt(
    input_path,
    output_path,
    passlog_path,
    media,
    plan,
    *,
    runner,
    progress,
    cancel,
    verifier,
    warnings,
    target_bytes,
    do_verify,
):
    with TempOutput(output_path) as temp_path:
        job = ProductEncodeJob(input_path, temp_path, passlog_path, media, plan)
        commands = build_product_commands(job)
        for command in commands:
            _add_warnings(warnings, command.warnings)
        _run_commands(commands, media.duration, runner, progress, cancel)

        output_size = _file_size(temp_path)
        if target_bytes is not None and not within_cap(output_size, target_bytes):
            raise _SizeExceeded(output_size)

        if do_verify:
            verification = verifier(
                temp_path, media.duration, media.audio_tracks
            )
            if not verification.ok:
                raise _VerificationFailed(verification)

    return commands, output_size


def _run_fallback(
    request,
    input_path,
    output_path,
    passlog_path,
    media,
    profile,
    resolution,
    target_bytes,
    original_size,
    *,
    runner,
    verifier,
    progress,
    cancel,
    warnings,
):
    plan = EncodePlan(
        encoder="libx264",
        encoder_preset="veryfast",
        resolution=resolution,
        crf=26,
        video_kbps=None,
        audio_bitrate=profile.audio_bitrate,
        keep_hdr=request.keep_hdr,
        keep_metadata=request.keep_metadata,
        compatibility=request.compatibility,
        target_bytes=None,
    )
    try:
        _commands, output_size = _encode_attempt(
            input_path,
            output_path,
            passlog_path,
            media,
            plan,
            runner=runner,
            progress=progress,
            cancel=cancel,
            verifier=verifier,
            warnings=warnings,
            target_bytes=target_bytes,
            do_verify=True,
        )
    except _SizeExceeded:
        cap_mb = target_bytes / (1024 * 1024)
        return _failure(
            output_path,
            original_size,
            "libx264",
            warnings,
            f"could not fit under {cap_mb:.2f} MB",
        )
    except _VerificationFailed as exc:
        reasons = "; ".join(exc.result.reasons) or "verification failed"
        return _failure(
            output_path,
            original_size,
            "libx264",
            warnings,
            f"verification failed: {reasons}",
        )
    return _finish(
        input_path, output_path, original_size, output_size, "libx264", warnings
    )


def compress(
    request: CompressRequest,
    *,
    progress=None,
    cancel=None,
    prober=probe,
    detector=detect_encoders,
    runner=run_with_progress,
    verifier=verify_output,
    encoder_chooser=choose_encoder,
) -> CompressResult:
    input_path = request.input_path
    output_path = request.output_path
    warnings = []

    if not os.path.exists(input_path):
        return _failure(
            output_path,
            0,
            "",
            warnings,
            f"input file does not exist: {input_path}",
        )

    if os.path.realpath(output_path) == os.path.realpath(input_path):
        return _failure(
            output_path,
            _file_size(input_path),
            "",
            warnings,
            "input and output paths must differ",
        )

    original_size = _file_size(input_path)

    if os.path.exists(output_path) and not request.overwrite:
        output_size = _file_size(output_path)
        return CompressResult(
            ok=True,
            output_path=output_path,
            original_size=original_size,
            output_size=output_size,
            saved_percent=_saved_percent(original_size, output_size),
            encoder="",
            warnings=(),
            skipped=True,
        )

    try:
        profile = resolve_profile(
            request.profile,
            target_mb=request.target_mb,
            speed=request.speed,
            codec=request.codec,
        )
    except ValueError as exc:
        return _failure(output_path, original_size, "", warnings, str(exc))

    media = prober(input_path)

    if profile.target_bytes is not None and media.duration <= 0:
        return _failure(
            output_path,
            original_size,
            "",
            warnings,
            "could not determine duration for a size cap",
        )

    if (
        profile.target_bytes is not None
        and original_size <= profile.target_bytes
    ):
        return CompressResult(
            ok=True,
            output_path=input_path,
            original_size=original_size,
            output_size=original_size,
            saved_percent=0.0,
            encoder="",
            warnings=(),
            already_small=True,
        )

    allow_hardware = (
        profile.target_bytes is None
        and profile.name in _SHARING_PROFILES
        and profile.speed != "smallest"
        and not request.keep_hdr
    )

    try:
        available = detector()
        encoder = encoder_chooser(
            profile.codec,
            profile.speed,
            available,
            allow_hardware=allow_hardware,
        )
    except (RuntimeError, ValueError) as exc:
        return _failure(output_path, original_size, "", warnings, str(exc))

    target_bytes = profile.target_bytes
    if target_bytes is not None and _is_hardware_encoder(encoder):
        encoder = _SOFTWARE_FALLBACK[profile.codec]

    if target_bytes is not None:
        try:
            size_plan = plan_size(
                media.duration, target_bytes, media.audio_tracks
            )
        except ValueError as exc:
            return _failure(
                output_path, original_size, encoder, warnings, str(exc)
            )
        video_kbps = size_plan.video_kbps
        crf = None
    elif _is_hardware_encoder(encoder):
        video_kbps = _HARDWARE_RESOLUTION_KBPS.get(
            profile.resolution, _DEFAULT_HARDWARE_KBPS
        )
        crf = None
    else:
        video_kbps = None
        crf = _SOFTWARE_CRF.get(profile.name, _DEFAULT_CRF)

    passlog_path = _passlog_path(output_path)

    try:
        if request.dry_run:
            plan = _make_plan(
                encoder,
                profile,
                profile.resolution,
                crf,
                video_kbps,
                target_bytes,
                request,
            )
            job = ProductEncodeJob(
                input_path, output_path, passlog_path, media, plan
            )
            commands = build_product_commands(job)
            for command in commands:
                _add_warnings(warnings, command.warnings)
            return CompressResult(
                ok=True,
                output_path=output_path,
                original_size=original_size,
                output_size=0,
                saved_percent=0.0,
                encoder=encoder,
                warnings=tuple(warnings),
                planned_commands=tuple(
                    " ".join(command.args) for command in commands
                ),
            )

        if target_bytes is not None:
            attempts = 0
            current_resolution = profile.resolution
            current_kbps = video_kbps
            while attempts < _MAX_ATTEMPTS:
                attempts += 1
                plan = _make_plan(
                    encoder,
                    profile,
                    current_resolution,
                    None,
                    current_kbps,
                    target_bytes,
                    request,
                )
                try:
                    _commands, output_size = _encode_attempt(
                        input_path,
                        output_path,
                        passlog_path,
                        media,
                        plan,
                        runner=runner,
                        progress=progress,
                        cancel=cancel,
                        verifier=verifier,
                        warnings=warnings,
                        target_bytes=target_bytes,
                        do_verify=request.verify,
                    )
                except _SizeExceeded as exc:
                    if attempts >= _MAX_ATTEMPTS:
                        cap_mb = target_bytes / (1024 * 1024)
                        return _failure(
                            output_path,
                            original_size,
                            encoder,
                            warnings,
                            f"could not fit under {cap_mb:.2f} MB",
                        )
                    _cleanup_passlog(passlog_path)
                    if attempts == _MAX_ATTEMPTS - 1:
                        current_resolution = _drop_resolution(
                            current_resolution
                        )
                    current_kbps = next_bitrate(
                        exc.actual_bytes, target_bytes, current_kbps
                    )
                    continue
                except _VerificationFailed:
                    return _run_fallback(
                        request,
                        input_path,
                        output_path,
                        passlog_path,
                        media,
                        profile,
                        current_resolution,
                        target_bytes,
                        original_size,
                        runner=runner,
                        verifier=verifier,
                        progress=progress,
                        cancel=cancel,
                        warnings=warnings,
                    )
                return _finish(
                    input_path,
                    output_path,
                    original_size,
                    output_size,
                    encoder,
                    warnings,
                )

        plan = _make_plan(
            encoder,
            profile,
            profile.resolution,
            crf,
            video_kbps,
            None,
            request,
        )
        try:
            _commands, output_size = _encode_attempt(
                input_path,
                output_path,
                passlog_path,
                media,
                plan,
                runner=runner,
                progress=progress,
                cancel=cancel,
                verifier=verifier,
                warnings=warnings,
                target_bytes=None,
                do_verify=request.verify,
            )
        except _VerificationFailed:
            return _run_fallback(
                request,
                input_path,
                output_path,
                passlog_path,
                media,
                profile,
                profile.resolution,
                None,
                original_size,
                runner=runner,
                verifier=verifier,
                progress=progress,
                cancel=cancel,
                warnings=warnings,
            )
        return _finish(
            input_path,
            output_path,
            original_size,
            output_size,
            encoder,
            warnings,
        )
    except Cancelled:
        return _failure(
            output_path, original_size, encoder, warnings, "cancelled"
        )
    finally:
        _cleanup_passlog(passlog_path)
