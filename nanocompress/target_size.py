from dataclasses import dataclass

MIN_VIDEO_KBPS = 50
RETRY_SAFETY = 0.98


@dataclass(frozen=True)
class SizePlan:
    target_bytes: int
    budget_bytes: int
    video_kbps: int
    audio_kbps: int
    audio_tracks: int


def plan_size(
    duration_s: float,
    target_bytes: int,
    audio_tracks: int,
    *,
    audio_kbps: int = 64,
    margin: float = 0.95,
    overhead: float = 0.02,
) -> SizePlan:
    if duration_s <= 0:
        raise ValueError("duration must be greater than zero")
    if target_bytes <= 0:
        raise ValueError("target size must be greater than zero")
    if audio_tracks < 0:
        raise ValueError("audio track count cannot be negative")
    if audio_kbps <= 0:
        raise ValueError("audio bitrate must be greater than zero")
    if margin <= 0:
        raise ValueError("margin must be greater than zero")

    budget_bytes = int(target_bytes * margin * (1 - overhead))
    total_kbps = budget_bytes * 8 / duration_s / 1000
    video_kbps = int(total_kbps - audio_kbps * audio_tracks)
    if video_kbps < MIN_VIDEO_KBPS:
        raise ValueError(
            f"target too small: video bitrate {video_kbps} kbps "
            f"is below the {MIN_VIDEO_KBPS} kbps minimum"
        )

    return SizePlan(
        target_bytes=target_bytes,
        budget_bytes=budget_bytes,
        video_kbps=video_kbps,
        audio_kbps=audio_kbps,
        audio_tracks=audio_tracks,
    )


def within_cap(actual_bytes: int, target_bytes: int) -> bool:
    return actual_bytes <= target_bytes


def next_bitrate(actual_bytes: int, target_bytes: int, current_kbps: int) -> int:
    if actual_bytes <= 0:
        return current_kbps
    return max(MIN_VIDEO_KBPS, int(current_kbps * target_bytes / actual_bytes * RETRY_SAFETY))
