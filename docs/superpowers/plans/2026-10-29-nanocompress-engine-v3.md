# NanoCompress Engine v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing CLI engine into a product-grade compression API that supports purpose presets, hard size caps, hardware-aware speed, SDR/HDR policy, metadata privacy, output verification, progress, and cancellation.

**Architecture:** A new product layer (`presets`, `encoders`, `target_size`, `process`, `verify`, `compress`) sits on top of the existing probe/command/jobs code. The legacy CLI path stays intact; a new `--profile` path calls the new `compress()` API. All encoding still goes through `ffmpeg`/`ffprobe` as child processes.

**Tech Stack:** Python 3.8+ standard library only; FFmpeg/ffprobe; `unittest`; no third-party packages.

**Spec:** `docs/superpowers/specs/2026-10-29-nanocompress-product-design.md`

## Scope Check

The design covers several independent subsystems: engine, desktop GUI, packaging, release, and adoption. This plan covers **only the engine (v3)**. It produces working, testable software on its own: a `compress()` API plus CLI flags. GUI, packaging, and launch get separate plans after this one ships.

## Global Constraints

- Python 3.8+ standard library only; no pip dependencies.
- FFmpeg and ffprobe are external executables; never use `shell=True`.
- Output is MP4 with `-movflags +faststart`.
- Sharing presets default to H.264 8-bit SDR, AAC-LC.
- Save-storage defaults to HEVC 8-bit SDR, `-tag:v hvc1`.
- HDR is SDR by default; `keep_hdr` preserves HDR10/HLG only; Dolby Vision is always SDR in v1.
- A size cap is hard: aim for 95% of the cap, retry at most 3 times, never exceed it.
- Preserve source timestamps by default; compatibility mode may force CFR 30.
- Never silently drop an audio track or text subtitle; image subtitles are skipped with a warning.
- Never overwrite the source; never return a file larger than the source.
- Tests run with `python -m unittest discover -s tests -v`.
- Execute this plan in a feature worktree created via `superpowers:using-git-worktrees`.

## File Structure

- Create `nanocompress/presets.py` — product profiles and speed mapping.
- Create `nanocompress/encoders.py` — encoder discovery and selection.
- Create `nanocompress/target_size.py` — bitrate budgeting and retry math.
- Create `nanocompress/process.py` — FFmpeg progress parsing and cancellation.
- Create `nanocompress/verify.py` — output validation and fallback decision.
- Create `nanocompress/compress.py` — orchestration API.
- Modify `nanocompress/probe.py` — average frame rate and Dolby Vision detection.
- Modify `nanocompress/command.py` — product command builder.
- Modify `nanocompress/runner.py` — dry-run summary fix.
- Modify `compressor.py` — new product CLI flags.
- Create `tests/test_presets.py`, `tests/test_encoders.py`, `tests/test_target_size.py`, `tests/test_process.py`, `tests/test_verify.py`, `tests/test_compress.py`, `tests/test_integration_phone.py`.
- Modify `tests/test_probe.py`, `tests/test_command.py`, `tests/test_cli.py`.

## Review Focus

These are the failure modes most likely to bite a real user. Each gets a test in the task that owns the code.

1. **Already-small input:** a 5 MB clip with a 10 MB cap must return the original with "already small enough", not a larger re-encode and not an overwrite. (Task 8)
2. **Awkward phone video:** rotated HEVC 10-bit HDR/Dolby Vision VFR clip with GPS metadata must come out upright, SDR by default, GPS-free, and playable. (Tasks 2, 5, 10)
3. **Impossible hard cap:** a 1-hour clip with a 10 MB cap must never exceed the cap; after retries it must fail with a clear message. (Task 8)
4. **Multiple audio tracks and image subtitles:** all audio and text subtitles preserved; image subtitles skipped with a per-stream warning. (Tasks 5, 10)
5. **No hardware encoder or no zscale:** graceful software fallback, or a clear error; cancel mid-encode leaves no partial output. (Tasks 3, 6, 7)

---

### Task 1: Product presets and speed mapping

**Files:**
- Create: `nanocompress/presets.py`
- Test: `tests/test_presets.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `SPEEDS = ("fast", "balanced", "smallest")`
  - `PROFILES = ("send", "discord", "email", "storage", "custom")`
  - `@dataclass(frozen=True) class Profile: name: str; speed: str; resolution: int; codec: str; target_bytes: Optional[int]; audio_bitrate: str`
  - `resolve_profile(name: str, *, target_mb: Optional[float] = None, speed: Optional[str] = None, codec: Optional[str] = None) -> Profile`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_presets.py
import unittest

from nanocompress.presets import Profile, resolve_profile


class ResolveProfileTests(unittest.TestCase):
    def test_send_defaults_to_fast_h264_720p(self):
        p = resolve_profile("send")
        self.assertEqual((p.speed, p.codec, p.resolution), ("fast", "h264", 720))
        self.assertIsNone(p.target_bytes)

    def test_discord_is_a_10mb_cap(self):
        self.assertEqual(resolve_profile("discord").target_bytes, 10 * 1024 * 1024)

    def test_email_is_a_25mb_cap(self):
        self.assertEqual(resolve_profile("email").target_bytes, 25 * 1024 * 1024)

    def test_storage_is_balanced_hevc_480p(self):
        p = resolve_profile("storage")
        self.assertEqual((p.speed, p.codec, p.resolution), ("balanced", "hevc", 480))

    def test_custom_requires_a_target(self):
        with self.assertRaises(ValueError):
            resolve_profile("custom")
        self.assertEqual(resolve_profile("custom", target_mb=7.5).target_bytes, 7864320)

    def test_target_mb_overrides_the_profile_cap(self):
        self.assertEqual(resolve_profile("discord", target_mb=1).target_bytes, 1024 * 1024)

    def test_speed_and_codec_overrides(self):
        p = resolve_profile("send", speed="smallest", codec="hevc")
        self.assertEqual((p.speed, p.codec), ("smallest", "hevc"))

    def test_unknown_profile_speed_and_codec_fail(self):
        for kwargs in ({"name": "nope"}, {"name": "send", "speed": "warp"},
                       {"name": "send", "codec": "av1"}):
            with self.assertRaises(ValueError):
                resolve_profile(**kwargs)

    def test_negative_target_fails(self):
        with self.assertRaises(ValueError):
            resolve_profile("custom", target_mb=-1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_presets -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nanocompress.presets'`

- [ ] **Step 3: Implement `resolve_profile`**

Create the module with the constants and frozen dataclass above. Defaults:

| Profile | Speed | Resolution | Codec | Target |
|---|---|---|---|---|
| send | fast | 720 | h264 | none |
| discord | fast | 480 | h264 | 10 MB |
| email | fast | 540 | h264 | 25 MB |
| storage | balanced | 480 | hevc | none |
| custom | fast | 720 | h264 | required |

Rules: `target_mb` is converted with `int(round(target_mb * 1024 * 1024))`; `"auto"` resolves to the profile codec; unknown names/speeds/codecs raise `ValueError`; non-positive targets raise `ValueError`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_presets -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add nanocompress/presets.py tests/test_presets.py
git commit -m "feat: add product compression profiles"
```

---

### Task 2: Probe average frame rate and Dolby Vision

**Files:**
- Modify: `nanocompress/probe.py`
- Modify: `tests/test_probe.py`

**Interfaces:**
- Consumes: existing `MediaInfo`, `parse_media_info`.
- Produces:
  - `MediaInfo.avg_frame_rate: str = ""`
  - `MediaInfo.is_dolby_vision: bool = False`
  - `is_dolby_vision_stream(stream: dict) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_probe.py
from nanocompress.probe import is_dolby_vision_stream

class DolbyVisionTests(unittest.TestCase):
    def test_dvhe_tag_is_dolby_vision(self):
        self.assertTrue(is_dolby_vision_stream({"codec_tag_string": "dvhe"}))

    def test_dovi_side_data_is_dolby_vision(self):
        stream = {"side_data_list": [{"side_data_type": "DOVI configuration record"}]}
        self.assertTrue(is_dolby_vision_stream(stream))

    def test_plain_hevc_is_not_dolby_vision(self):
        self.assertFalse(is_dolby_vision_stream({"codec_tag_string": "hvc1"}))

    def test_avg_frame_rate_is_parsed(self):
        data = {"format": {"duration": "1.0"}, "streams": [{
            "codec_type": "video", "width": 10, "height": 10,
            "codec_name": "hevc", "avg_frame_rate": "30000/1001",
        }]}
        self.assertEqual(parse_media_info(data).avg_frame_rate, "30000/1001")

    def test_dolby_vision_flag_is_parsed(self):
        data = {"format": {"duration": "1.0"}, "streams": [{
            "codec_type": "video", "width": 10, "height": 10,
            "codec_name": "hevc", "codec_tag_string": "dvhe",
        }]}
        self.assertTrue(parse_media_info(data).is_dolby_vision)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_probe -v`
Expected: FAIL with `ImportError: cannot import name 'is_dolby_vision_stream'`

- [ ] **Step 3: Implement the fields and parser**

Add the two defaulted fields to the end of `MediaInfo`. Implement `is_dolby_vision_stream` using tags `{"dvh1", "dvhe", "dvav", "dva1"}` or side data `"DOVI configuration record"`. In `parse_media_info`, set `avg_frame_rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or ""` and `is_dolby_vision = is_dolby_vision_stream(video)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_probe -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/probe.py tests/test_probe.py
git commit -m "feat: detect average frame rate and Dolby Vision"
```

---

### Task 3: Encoder discovery and selection

**Files:**
- Create: `nanocompress/encoders.py`
- Test: `tests/test_encoders.py`

**Interfaces:**
- Consumes: `ffmpeg -encoders` output.
- Produces:
  - `@dataclass(frozen=True) class Encoder: name: str; codec: str; hardware: bool`
  - `parse_encoders(text: str) -> tuple[Encoder, ...]`
  - `detect_encoders(runner=subprocess.run) -> tuple[Encoder, ...]`
  - `choose_encoder(codec: str, speed: str, available: tuple[Encoder, ...], *, platform: str = sys.platform, allow_hardware: bool = True) -> str`
  - `encoder_preset(speed: str, codec: str) -> str`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_encoders.py
import unittest

from nanocompress.encoders import Encoder, choose_encoder, encoder_preset, parse_encoders

SAMPLE = """
 V....D libx264              libx264 H.264 (codec h264)
 V....D libx265              libx265 H.265 (codec hevc)
 V....D h264_nvenc           NVIDIA NVENC H.264 encoder
 V....D hevc_videotoolbox    VideoToolbox H.265 encoder
"""


class ParseTests(unittest.TestCase):
    def test_parses_software_and_hardware(self):
        names = {e.name for e in parse_encoders(SAMPLE)}
        self.assertIn("libx264", names)
        self.assertIn("h264_nvenc", names)
        self.assertIn("hevc_videotoolbox", names)

    def test_flags_hardware(self):
        by_name = {e.name: e for e in parse_encoders(SAMPLE)}
        self.assertFalse(by_name["libx264"].hardware)
        self.assertTrue(by_name["h264_nvenc"].hardware)


class ChooseTests(unittest.TestCase):
    def setUp(self):
        self.available = parse_encoders(SAMPLE)

    def test_fast_prefers_hardware(self):
        self.assertEqual(choose_encoder("h264", "fast", self.available, platform="linux"),
                         "h264_nvenc")

    def test_smallest_never_uses_hardware(self):
        self.assertEqual(choose_encoder("hevc", "smallest", self.available, platform="darwin"),
                         "libx265")

    def test_allow_hardware_false_falls_back_to_software(self):
        self.assertEqual(choose_encoder("h264", "fast", self.available,
                                        platform="linux", allow_hardware=False),
                         "libx264")

    def test_no_usable_encoder_raises(self):
        with self.assertRaises(RuntimeError):
            choose_encoder("h264", "fast", (), platform="linux")


class PresetTests(unittest.TestCase):
    def test_presets(self):
        self.assertEqual(encoder_preset("fast", "h264"), "veryfast")
        self.assertEqual(encoder_preset("balanced", "hevc"), "medium")
        self.assertEqual(encoder_preset("smallest", "hevc"), "slow")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_encoders -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement discovery and selection**

Parse lines matching `^\s*[VAS][A-Z.]{5}\s+(\S+)` and map names containing `libx264`/`libx265` to software, and `_nvenc`, `_qsv`, `_videotoolbox`, `_amf`, `_vaapi` to hardware with the codec from the prefix. `detect_encoders` runs `["ffmpeg", "-hide_banner", "-encoders"]` with `capture_output=True, text=True, check=True`.

`choose_encoder` rules:
- `speed == "smallest"` or `allow_hardware is False` → software only.
- Otherwise prefer platform hardware in this order: darwin `videotoolbox`; linux `nvenc`, `qsv` (VAAPI is detected but not selected in v1 because it needs explicit device/upload handling); win32 `nvenc`, `qsv`, `amf`.
- Fall back to `libx264`/`libx265`; raise `RuntimeError` if neither exists.

`encoder_preset`: fast → `veryfast` for h264, `fast` for hevc; balanced → `medium`; smallest → `slow`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_encoders -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/encoders.py tests/test_encoders.py
git commit -m "feat: detect and choose hardware encoders"
```

---

### Task 4: Size budget and retry math

**Files:**
- Create: `nanocompress/target_size.py`
- Test: `tests/test_target_size.py`

**Interfaces:**
- Consumes: duration, target bytes, audio track count.
- Produces:
  - `@dataclass(frozen=True) class SizePlan: target_bytes: int; budget_bytes: int; video_kbps: int; audio_kbps: int; audio_tracks: int`
  - `plan_size(duration_s: float, target_bytes: int, audio_tracks: int, *, audio_kbps: int = 64, margin: float = 0.95, overhead: float = 0.02) -> SizePlan`
  - `within_cap(actual_bytes: int, target_bytes: int) -> bool`
  - `next_bitrate(actual_bytes: int, target_bytes: int, current_kbps: int) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_target_size.py
import unittest

from nanocompress.target_size import next_bitrate, plan_size, within_cap


class PlanSizeTests(unittest.TestCase):
    def test_10mb_60s_one_audio_track(self):
        plan = plan_size(60.0, 10 * 1024 * 1024, 1)
        self.assertEqual(plan.budget_bytes, 9762242)
        self.assertEqual(plan.video_kbps, 1237)
        self.assertEqual(plan.audio_kbps, 64)

    def test_more_audio_tracks_lower_video_bitrate(self):
        one = plan_size(60.0, 10 * 1024 * 1024, 1)
        two = plan_size(60.0, 10 * 1024 * 1024, 2)
        self.assertLess(two.video_kbps, one.video_kbps)

    def test_impossible_target_raises(self):
        with self.assertRaises(ValueError):
            plan_size(600.0, 100 * 1024, 1)

    def test_invalid_inputs_raise(self):
        for args in ((0, 1024 * 1024, 1), (60, 0, 1), (60, 1024, -1)):
            with self.assertRaises(ValueError):
                plan_size(*args)


class RetryTests(unittest.TestCase):
    def test_within_cap(self):
        self.assertTrue(within_cap(100, 100))
        self.assertFalse(within_cap(101, 100))

    def test_next_bitrate_scales_down(self):
        self.assertEqual(next_bitrate(120, 100, 1000), 816)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_target_size -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the budget math**

`budget_bytes = int(target_bytes * margin * (1 - overhead))`.
`total_kbps = budget_bytes * 8 / duration_s / 1000`.
`video_kbps = int(total_kbps - audio_kbps * audio_tracks)`.
Raise `ValueError` if any input is non-positive, audio tracks are negative, or `video_kbps < 50`.
`within_cap` is `actual_bytes <= target_bytes`.
`next_bitrate` is `max(50, int(current_kbps * target_bytes / actual_bytes * 0.98))`; if `actual_bytes <= 0`, return `current_kbps`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_target_size -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/target_size.py tests/test_target_size.py
git commit -m "feat: add hard size-cap budgeting"
```

---

### Task 5: Product command builder

**Files:**
- Modify: `nanocompress/command.py`
- Modify: `tests/test_command.py`

**Interfaces:**
- Consumes: `MediaInfo`, `Options` (legacy only), new plan fields.
- Produces:
  - `@dataclass(frozen=True) class EncodePlan: encoder: str; encoder_preset: str; resolution: int; crf: Optional[int]; video_kbps: Optional[int]; audio_bitrate: str; keep_hdr: bool; keep_metadata: bool; compatibility: bool; target_bytes: Optional[int]`
  - `@dataclass(frozen=True) class ProductEncodeJob: input_path: str; output_path: str; passlog_path: str; media: MediaInfo; plan: EncodePlan`
  - `build_product_commands(job: ProductEncodeJob) -> tuple[Command, ...]`

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_command.py
from nanocompress.command import (
    EncodePlan, ProductEncodeJob, build_product_commands,
)

def product_job(media_info=None, **plan_kw):
    plan = dict(encoder="libx264", encoder_preset="veryfast", resolution=720,
                crf=26, video_kbps=None, audio_bitrate="64k",
                keep_hdr=False, keep_metadata=False, compatibility=False,
                target_bytes=None)
    plan.update(plan_kw)
    return ProductEncodeJob("in.mp4", "/tmp/out.mp4", "/tmp/passlog",
                            media_info or media(), EncodePlan(**plan))


class ProductCommandTests(unittest.TestCase):
    def test_sdr_default_strips_metadata_and_scales(self):
        m = media(width=1920, height=1080, sample_aspect_ratio="1:1")
        cmd = build_product_commands(product_job(m))[0].args
        filters = cmd[cmd.index("-vf") + 1]
        self.assertIn("scale=1280:720:flags=lanczos", filters)
        self.assertNotIn("zscale", filters)
        self.assertIn("-map_metadata", cmd)
        self.assertEqual(cmd[cmd.index("-map_metadata") + 1], "-1")
        self.assertIn("+faststart", cmd)

    def test_keep_metadata_maps_source_metadata(self):
        cmd = build_product_commands(product_job(keep_metadata=True))[0].args
        self.assertEqual(cmd[cmd.index("-map_metadata") + 1], "0")

    def test_hdr_default_tonemaps_to_sdr(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        cmd = build_product_commands(product_job(m))[0].args
        self.assertIn("zscale", " ".join(cmd))
        self.assertIn("yuv420p", cmd)
        self.assertNotIn("-color_primaries", cmd)

    def test_keep_hdr_preserves_10bit_and_metadata(self):
        m = media(is_hdr=True, color_transfer="smpte2084", color_primaries="bt2020")
        cmd = build_product_commands(product_job(m, keep_hdr=True, encoder="libx265"))[0].args
        self.assertNotIn("zscale", " ".join(cmd))
        self.assertIn("yuv420p10le", cmd)
        self.assertIn("-color_primaries", cmd)
        self.assertIn("hvc1", cmd)

    def test_dolby_vision_always_tonemaps_and_warns(self):
        m = media(is_hdr=True, is_dolby_vision=True)
        result = build_product_commands(product_job(m, keep_hdr=True, encoder="libx265"))[0]
        self.assertIn("zscale", " ".join(result.args))
        self.assertTrue(any("Dolby Vision" in w for w in result.warnings))

    def test_compatibility_forces_cfr_30(self):
        cmd = build_product_commands(product_job(compatibility=True))[0].args
        self.assertIn("fps=30", cmd[cmd.index("-vf") + 1])

    def test_default_preserves_vfr_timestamps(self):
        cmd = build_product_commands(product_job())[0].args
        self.assertNotIn("fps=", " ".join(cmd))

    def test_hardware_bitrate_mode(self):
        cmd = build_product_commands(product_job(encoder="h264_nvenc", crf=None,
                                                 video_kbps=1000))[0].args
        self.assertIn("h264_nvenc", cmd)
        self.assertIn("-b:v", cmd)
        self.assertNotIn("-crf", cmd)
        self.assertNotIn("-preset", cmd)

    def test_target_size_uses_two_passes(self):
        commands = build_product_commands(product_job(crf=None, video_kbps=1237,
                                                      target_bytes=10 * 1024 * 1024))
        self.assertEqual(len(commands), 2)
        self.assertIn("-pass", commands[0].args)
        self.assertEqual(commands[0].args[commands[0].args.index("-pass") + 1], "1")
        self.assertIn("-f", commands[0].args)
        self.assertIn("null", commands[0].args)
        self.assertEqual(commands[1].args[commands[1].args.index("-pass") + 1], "2")

    def test_maps_all_audio_and_text_subtitles(self):
        m = media(subtitles=(Subtitle(2, "subrip"), Subtitle(5, "hdmv_pgs_subtitle")))
        result = build_product_commands(product_job(m))[0]
        self.assertIn("0:a?", result.args)
        self.assertIn("0:2", result.args)
        self.assertNotIn("0:5", result.args)
        self.assertTrue(any("image-based" in w for w in result.warnings))
```

Add `is_dolby_vision` to the `media()` helper defaults in `tests/test_command.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_command -v`
Expected: FAIL with `ImportError: cannot import name 'EncodePlan'`

- [ ] **Step 3: Implement `build_product_commands`**

Rules:
- Tone-map when `media.is_hdr and not keep_hdr`, or when `media.is_dolby_vision` (always in v1). Warn on Dolby Vision.
- Filter chain: tone-map (`zscale` chain + `format=yuv420p`), optional `fps=30` when `compatibility`, then `scale=<width>:<resolution>:flags=lanczos,setsar=1`. Reuse `target_width`.
- Pixel format: `yuv420p10le` only when `keep_hdr` and the source is HDR and not Dolby Vision and not tone-mapped; otherwise `yuv420p`.
- Metadata: `-map_metadata -1` and `-map_chapters -1` unless `keep_metadata`, then `-map_metadata 0` and `-map_chapters 0`.
- Maps: first video, all audio (`0:a?`), each text subtitle by absolute index; warn for image subtitles.
- Video:
  - CRF mode (`crf is not None`): `-c:v <encoder> -crf <crf> -preset <encoder_preset>`.
  - Hardware bitrate mode (`video_kbps is not None`, `target_bytes is None`): `-c:v <encoder> -b:v <kbps>k -maxrate <kbps*1.2>k -bufsize <kbps*2>k`. Do not emit `-preset`; hardware encoders have their own preset scales.
  - Target mode (`video_kbps is not None`, `target_bytes is not None`): two commands. Pass 1: `-pass 1 -passlogfile <path> -an -sn -f null -` (no output path, no audio/subtitle/output flags), same video flags. Pass 2: `-pass 2 -passlogfile <path>` plus audio/subtitle/output flags and the output path. Only pass 2 gets `+faststart`. Software encoders only; raise `ValueError` if `encoder` is hardware.
- HEVC: add `-tag:v hvc1`; keep HDR color metadata and `-x265-params` (master-display/max-cll) as the existing builder does.
- Audio/subtitles/output: `-c:a aac -b:a <audio_bitrate>`, `-c:s mov_text` when text subs exist, `-movflags +faststart`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_command -v`
Expected: PASS (existing plus new tests)

- [ ] **Step 5: Commit**

```bash
git add nanocompress/command.py tests/test_command.py
git commit -m "feat: build product compression commands"
```

---

### Task 6: Progress parsing and cancellation

**Files:**
- Create: `nanocompress/process.py`
- Test: `tests/test_process.py`

**Interfaces:**
- Consumes: an argument list, clip duration.
- Produces:
  - `@dataclass(frozen=True) class Progress: percent: float; seconds: float; speed: str`
  - `class Cancelled(Exception)`
  - `run_with_progress(args: list[str], duration_s: float, *, progress: Optional[Callable[[Progress], None]] = None, cancel: Optional[threading.Event] = None) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_process.py
import os, sys, tempfile, threading, time, unittest
from nanocompress.process import Cancelled, Progress, run_with_progress

FAKE = """
import sys, time
for pct in (10, 50, 100):
    print(f"out_time_ms={pct * 1000000}", flush=True)
    print(f"speed=1.0x", flush=True)
    print(f"progress={'end' if pct == 100 else 'continue'}", flush=True)
    time.sleep(0.01)
"""

SLOW = """
import time
time.sleep(30)
"""


class ProgressTests(unittest.TestCase):
    def _script(self, body):
        path = os.path.join(tempfile.mkdtemp(), "fake.py")
        with open(path, "w") as handle:
            handle.write(body)
        return [sys.executable, path]

    def test_reports_percentages(self):
        seen = []
        code = run_with_progress(self._script(FAKE), 100.0,
                                 progress=lambda p: seen.append(round(p.percent)))
        self.assertEqual(code, 0)
        self.assertEqual(seen, [10, 50, 100])

    def test_cancel_raises_and_stops_the_process(self):
        event = threading.Event()
        threading.Timer(0.2, event.set).start()
        with self.assertRaises(Cancelled):
            run_with_progress(self._script(SLOW), 100.0, cancel=event)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_process -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the runner**

Insert `["-progress", "pipe:1", "-nostats"]` immediately after the executable name (before all other arguments, so it stays a global option). Start `subprocess.Popen(args, stdout=PIPE, stderr=STDOUT, text=True, bufsize=1)`. A reader thread pushes lines to a `queue.Queue`. The main loop polls the queue every 0.1 s; on `cancel.is_set()`, call `terminate()`, wait 5 s, then `kill()`, and raise `Cancelled`. Parse `out_time_ms`, `out_time_us`, `speed`, and `progress=end`; ignore malformed lines. Percent is `min(100.0, seconds / duration_s * 100)`; never divide by zero.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_process -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/process.py tests/test_process.py
git commit -m "feat: stream ffmpeg progress and support cancellation"
```

---

### Task 7: Output verification

**Files:**
- Create: `nanocompress/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: an output path, expected duration, expected audio track count.
- Produces:
  - `@dataclass(frozen=True) class Verification: ok: bool; reasons: tuple[str, ...]; duration: float; video_codec: str; audio_tracks: int`
  - `verify_output(path: str, expected_duration: float, expected_audio_tracks: int, *, runner=subprocess.run) -> Verification`
  - `needs_h264_fallback(result: Verification) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_verify.py
import os, shutil, subprocess, tempfile, unittest
from nanocompress.verify import needs_h264_fallback, verify_output

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.clip = os.path.join(self.dir, "ok.mp4")
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=160x120:rate=24",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "1", "-c:v", "libx264", "-preset", "ultrafast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", self.clip,
        ], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_output_passes(self):
        result = verify_output(self.clip, 1.0, 1)
        self.assertTrue(result.ok, result.reasons)

    def test_missing_file_fails(self):
        result = verify_output(os.path.join(self.dir, "nope.mp4"), 1.0, 1)
        self.assertFalse(result.ok)
        self.assertIs(needs_h264_fallback(result), True)

    def test_corrupt_file_fails(self):
        bad = os.path.join(self.dir, "bad.mp4")
        with open(bad, "wb") as handle:
            handle.write(b"not a video")
        self.assertFalse(verify_output(bad, 1.0, 1).ok)

    def test_duration_mismatch_fails(self):
        self.assertFalse(verify_output(self.clip, 10.0, 1).ok)

    def test_audio_count_mismatch_fails(self):
        result = verify_output(self.clip, 1.0, 2)
        self.assertFalse(result.ok)
        self.assertTrue(any("audio" in reason for reason in result.reasons))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_verify -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement verification**

Use `ffprobe -v error -print_format json -show_format -show_streams <path>` via the injected runner. Fail when the file is missing/empty, ffprobe fails, there is no video stream, `abs(duration - expected_duration) > 1.0`, or the audio stream count differs. Then decode-check at 0%, 50%, and 90% of the duration with `ffmpeg -v error -ss <t> -t 1 -i <path> -f null -`; each nonzero exit adds a reason. Return all reasons. `needs_h264_fallback` returns `not result.ok`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_verify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/verify.py tests/test_verify.py
git commit -m "feat: verify output duration, streams, and decodability"
```

---

### Task 8: `compress()` orchestration

**Files:**
- Create: `nanocompress/compress.py`
- Test: `tests/test_compress.py`

**Interfaces:**
- Consumes: `presets.resolve_profile`, `probe.probe`, `encoders.detect_encoders`, `encoders.choose_encoder`, `encoders.encoder_preset`, `target_size.plan_size`, `command.build_product_commands`, `process.run_with_progress`, `verify.verify_output`, `jobs.TempOutput`.
- Produces:
  - `@dataclass(frozen=True) class CompressRequest: input_path: str; output_path: str; profile: str = "send"; target_mb: Optional[float] = None; speed: Optional[str] = None; codec: Optional[str] = None; keep_hdr: bool = False; keep_metadata: bool = False; compatibility: bool = False; overwrite: bool = False; dry_run: bool = False; verify: bool = True`
  - `@dataclass(frozen=True) class CompressResult: ok: bool; output_path: str; original_size: int; output_size: int; saved_percent: float; encoder: str; warnings: tuple[str, ...]; error: str = ""; skipped: bool = False; already_small: bool = False; planned_commands: tuple[str, ...] = ()`
  - `compress(request: CompressRequest, *, progress=None, cancel=None, prober=probe, detector=detect_encoders, runner=run_with_progress, verifier=verify_output, encoder_chooser=choose_encoder) -> CompressResult`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_compress.py
import os, tempfile, unittest
from nanocompress.compress import CompressRequest, compress
from nanocompress.encoders import Encoder
from nanocompress.probe import MediaInfo
from nanocompress.verify import Verification

MEDIA = MediaInfo(duration=60.0, width=1920, height=1080, video_codec="hevc",
                  sample_aspect_ratio="1:1", rotation=0, color_transfer="bt709",
                  color_primaries="bt709", is_hdr=False, is_interlaced=False,
                  audio_tracks=1, subtitles=())


class CompressTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.src = os.path.join(self.dir, "in.mp4")
        with open(self.src, "wb") as handle:
            handle.write(b"x" * (2 * 1024 * 1024))
        self.out = os.path.join(self.dir, "out.mp4")

    def tearDown(self):
        self.tmp.cleanup()

    def _request(self, **kw):
        base = dict(input_path=self.src, output_path=self.out, profile="send")
        base.update(kw)
        return CompressRequest(**base)

    def _runner(self, sizes):
        calls = []
        def run(args, duration, **kw):
            calls.append(args)
            if "-pass" in args and args[args.index("-pass") + 1] == "1":
                return 0
            path = args[-1]
            size = sizes.pop(0)
            with open(path, "wb") as handle:
                handle.write(b"x" * size)
            return 0
        return run, calls

    def test_output_equal_to_input_is_rejected(self):
        result = compress(self._request(output_path=self.src),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=lambda *a, **k: 0)
        self.assertFalse(result.ok)
        self.assertIn("differ", result.error.lower())

    def test_already_small_returns_original_without_encoding(self):
        run, calls = self._runner([])
        result = compress(self._request(profile="custom", target_mb=10),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run, verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.already_small)
        self.assertEqual(result.output_path, self.src)
        self.assertEqual(calls, [])

    def test_hard_cap_retries_and_never_exceeds(self):
        run, calls = self._runner([int(1.2 * 1024 * 1024), 900 * 1024])
        result = compress(self._request(profile="custom", target_mb=1),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run, verifier=lambda *a, **k: Verification(True, (), 60, "h264", 1))
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(result.output_size, 1024 * 1024)
        self.assertGreaterEqual(len(calls), 2)

    def test_failed_verification_falls_back_to_h264(self):
        run, calls = self._runner([900 * 1024, 900 * 1024])
        checked = []
        def verify(path, duration, audio, **kw):
            checked.append(path)
            return Verification(len(checked) > 1, (), 60, "h264", 1)
        result = compress(self._request(profile="storage"),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx265", "hevc", False),
                                            Encoder("libx264", "h264", False)),
                          runner=run, verifier=verify)
        self.assertTrue(result.ok, result.error)
        self.assertIn("libx264", " ".join(calls[-1]))

    def test_dry_run_returns_commands_and_writes_nothing(self):
        run, calls = self._runner([])
        result = compress(self._request(profile="custom", target_mb=1, dry_run=True),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertTrue(result.ok)
        self.assertFalse(os.path.exists(self.out))
        self.assertEqual(calls, [])
        self.assertTrue(any("-pass" in cmd for cmd in result.planned_commands))

    def test_cancel_reports_error_and_removes_partial(self):
        from nanocompress.process import Cancelled
        def run(args, duration, **kw):
            raise Cancelled()
        result = compress(self._request(profile="send"),
                          prober=lambda _: MEDIA,
                          detector=lambda: (Encoder("libx264", "h264", False),),
                          runner=run)
        self.assertFalse(result.ok)
        self.assertIn("cancel", result.error.lower())
        self.assertFalse(os.path.exists(self.out))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_compress -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `compress()`**

Flow:
1. Validate input exists and `os.path.realpath(output) != os.path.realpath(input)`; return `ok=False` with a clear error otherwise. If the output exists and `request.overwrite` is false, return `skipped=True` with `output_path=output`.
2. `profile = resolve_profile(request.profile, target_mb=request.target_mb, speed=request.speed, codec=request.codec)`.
3. `media = prober(input)`. If the profile has a target and `media.duration <= 0`, return `ok=False` with "could not determine duration for a size cap".
4. Already-small: if `profile.target_bytes` and `os.path.getsize(input) <= profile.target_bytes`, return `already_small=True`, `output_path=input`.
5. `available = detector()`; hardware is allowed only when there is no target cap, the profile is a sharing profile (`send`, `discord`, `email`), speed is not `smallest`, and `keep_hdr` is false; call `choose_encoder(profile.codec, profile.speed, available, allow_hardware=...)`.
6. Build the plan: target mode → `plan_size(media.duration, target, media.audio_tracks)`, `video_kbps`, `crf=None`, two passes, software only (if encoder is hardware, choose `libx264`/`libx265` instead). Non-target hardware → `video_kbps` default by resolution (720→1000, 540→800, 480→600), `crf=None`. Non-target software → `crf` mapping (`send` 26, `storage` 32), `video_kbps=None`.
7. Dry run: build commands, return `planned_commands` and `ok=True`, no writes.
8. Encode loop (max 3 attempts): use a passlog path in the output directory (`.nanocompress-pass`); wrap `TempOutput(output)`; for each command call `runner(cmd.args, media.duration, progress=progress)`; on retry, delete temp, remove `passlog`/`passlog.mbtree`, and rebuild with `next_bitrate`. For two-pass, wrap the callback so pass 1 reports 0–50% and pass 2 reports 50–100%. After 2 failed size checks, drop resolution one step (`720→540→480→360`) and recompute. If still over, return `ok=False` with a clear "could not fit under N MB" error.
9. Verify if `request.verify`; if not ok, encode a fresh temp with `libx264`, `crf=26`, `encoder_preset="veryfast"`, one pass, and replace the output only if that verifies. If that fails too, return `ok=False` with reasons.
10. After success, if `output_size >= original_size * 0.98`, delete the output and return `already_small=True` pointing at the original.
11. Catch `Cancelled` → `ok=False`, `error="cancelled"`; ensure temp cleanup.
12. Return sizes, percent saved, encoder, warnings.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_compress -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nanocompress/compress.py tests/test_compress.py
git commit -m "feat: orchestrate presets, size caps, retries, and fallback"
```

---

### Task 9: CLI product flags and dry-run fix

**Files:**
- Modify: `compressor.py`
- Modify: `nanocompress/runner.py`
- Modify: `tests/test_cli.py`

**Interfaces:**
- Consumes: `compress`, `CompressRequest`.
- Produces: CLI flags `--profile`, `--target-size`, `--speed`, `--keep-hdr`, `--keep-metadata`, `--compatibility`, `--no-verify`.

- [ ] **Step 1: Write the failing tests**

Also add `"-qp", "0"` to the `make_clip` command in `tests/test_cli.py` so the sample is reliably larger than the test cap (synthetic testsrc undershoots bitrate targets).

```python
# append to tests/test_cli.py
class ProductCliTests(unittest.TestCase):
    def test_dry_run_custom_cap_prints_two_passes_and_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src, seconds=3)
            out = os.path.join(tmp, "a_small.mp4")
            result = run_cli(src, out, "--profile", "custom", "--target-size", "0.3",
                             "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("-pass", result.stdout)
            self.assertIn("planned", result.stdout.lower())
            self.assertFalse(os.path.exists(out))

    def test_storage_profiles_uses_hevc(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src)
            result = run_cli(src, "--profile", "storage", "--dry-run")
            self.assertIn("libx265", result.stdout)

    def test_smallest_speed_uses_slow_preset(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "a.mp4")
            make_clip(src)
            result = run_cli(src, "--profile", "send", "--speed", "smallest", "--dry-run")
            self.assertIn("slow", result.stdout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_cli -v`
Expected: FAIL with unrecognized arguments `--profile`

- [ ] **Step 3: Implement the CLI path and summary fix**

Add the flags with choices from `PROFILES`/`SPEEDS`. If `--target-size` is given without `--profile`, use `custom`. When `--profile` or `--target-size` is present, call `compress()` per input from `plan_jobs`, collect the outcomes into `JobResult` objects, and reuse `format_summary`; for dry runs, print `planned_commands` and label the summary `planned`. The CLI keeps the existing `_nc.mp4` naming for both paths; the GUI plan will add `-small.mp4`. Keep the legacy path when neither flag is present. In `runner.py`, add `dry_run: bool = False` to `JobResult`; `format_summary` labels it `[planned]` and excludes it from size totals and the saved percentage. Dry-run output must contain the word `planned`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_cli -v`
Expected: PASS (existing plus new tests)

- [ ] **Step 5: Commit**

```bash
git add compressor.py nanocompress/runner.py tests/test_cli.py
git commit -m "feat: add product CLI flags and honest dry-run output"
```

---

### Task 10: Phone-video integration matrix and docs

**Files:**
- Create: `tests/test_integration_phone.py`
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-10-29-nanocompress-product-design.md` (status → Approved)

**Interfaces:**
- Consumes: `compress`, `CompressRequest`.
- Produces: end-to-end proof for the Review Focus cases.

- [ ] **Step 1: Write the failing integration tests**

```python
# tests/test_integration_phone.py
import json, os, shutil, subprocess, tempfile, unittest
from nanocompress.compress import CompressRequest, compress

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not available")
class PhoneIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _clip(self, name, extra=()):
        path = os.path.join(self.dir, name)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
            "-t", "2", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "10",
            "-pix_fmt", "yuv420p", "-c:a", "aac", *extra, path,
        ], check=True)
        return path

    def test_gps_metadata_is_stripped(self):
        src = self._clip("gps.mp4", ("-metadata", "location=+37.7-122.4/"))
        out = os.path.join(self.dir, "gps_small.mp4")
        result = compress(CompressRequest(src, out, profile="send", speed="smallest",
                                          codec="h264"))
        self.assertTrue(result.ok, result.error)
        tags = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                               "format_tags", "-of", "json", out],
                              capture_output=True, text=True, check=True).stdout
        self.assertNotIn("location", tags.lower())

    def test_target_size_is_never_exceeded(self):
        src = self._clip("cap.mp4")
        out = os.path.join(self.dir, "cap_small.mp4")
        result = compress(CompressRequest(src, out, profile="custom", target_mb=0.25))
        self.assertTrue(result.ok, result.error)
        self.assertLessEqual(os.path.getsize(out), int(0.25 * 1024 * 1024))

    def test_output_duration_matches_source_and_plays(self):
        src = self._clip("dur.mp4")
        out = os.path.join(self.dir, "dur_small.mp4")
        result = compress(CompressRequest(src, out, profile="send", codec="h264",
                                          speed="smallest"))
        self.assertTrue(result.ok, result.error)
        data = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_format",
                                          "-show_streams", "-of", "json", out],
                                         capture_output=True, text=True,
                                         check=True).stdout)
        self.assertAlmostEqual(float(data["format"]["duration"]), 2.0, delta=1.0)
        self.assertTrue(any(s["codec_type"] == "video" for s in data["streams"]))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_integration_phone -v`
Expected: FAIL until the earlier tasks are complete.

- [ ] **Step 3: Update README and design status**

Document `--profile`, `--target-size`, `--speed`, `--keep-hdr`, `--keep-metadata`, `--compatibility`, `--no-verify`, the hard-cap rule, the speed policy, and the "no upload" promise. Set the design doc status to `Approved`.

- [ ] **Step 4: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (all tests, no skips beyond missing-FFmpeg guards)

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration_phone.py README.md docs/superpowers/specs/2026-10-29-nanocompress-product-design.md
git commit -m "test: cover phone-video privacy, caps, and playability"
```

---

## Later Plans (not in this plan)

1. **Desktop MVP** — PySide6 window, drag/drop, queue, progress, cancel, results.
2. **Packaging and release** — bundle FFmpeg, PyInstaller/Nuitka, Windows/macOS CI, signing/notarization.
3. **Launch and adoption** — README/demo, Homebrew/winget, issue templates, Show HN.
4. **Later** — Linux AppImage, Tauri UI, hardware acceleration expansion, localization.

## Self-Review Notes

- Spec coverage: presets (Task 1), playback baseline and codec policy (Tasks 3, 5), exact size (Tasks 4, 8), HDR/DV (Tasks 2, 5), metadata (Tasks 5, 10), already-small (Task 8), VFR/timing (Tasks 5, 10), streams (Tasks 5, 10), progress/cancel (Task 6), verification (Tasks 7, 8), CLI (Task 9), speed policy (Tasks 3, 5, 8).
- Review Focus cases are pinned to Tasks 2/5/8/10 (awkward phone video), 8 (already-small, impossible cap), 5/10 (streams), and 3/6/7 (fallback, cancel).
- Interfaces are consistent: `Profile`, `Encoder`, `SizePlan`, `EncodePlan`, `ProductEncodeJob`, `Progress`, `Verification`, `CompressRequest`, `CompressResult` are each defined before use.
