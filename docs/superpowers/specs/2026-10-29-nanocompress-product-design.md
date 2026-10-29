# NanoCompress Product Design — "No-upload phone-video shrinker"

Date: 2026-10-29
Status: Draft for review

## Intent and why

NanoCompress today is a well-tested Python CLI engine (81 tests) that produces
small, playable MP4s. It has no product layer: a non-technical person cannot
install it, and its goal ("smallest practical MP4 at a user-chosen
resolution") is a technical spec, not a user need.

The product goal is to become the **default local tool for normal people who
need a phone or camera video to be smaller**, without uploading it, without
ads or watermarks, and without understanding codecs.

The user moment: someone has a 4K iPhone/Android/DSLR clip that is too large
to send, post, or keep. They want it small enough to share, still watchable,
and they do not want to think about resolution, bitrate, or CRF.

## Position

**The no-upload phone-video shrinker for normal people.**

One-click desktop app. Drag videos in, choose a purpose ("Send", "Discord",
"Email", "Save storage", or "fit under __ MB"), get a small, verified-playable
MP4. Everything runs locally. No account, no upload, no watermark, no ads.

Why this position:

- Existing simple tools are either online (privacy/limits), phone apps
  (ads/watermarks), or generic desktop wrappers (CompressO). HandBrake and
  Shutter Encoder are powerful but intimidating.
- "Phone video" is a real technical niche: HEVC, 10-bit, HDR/Dolby Vision,
  rotation, variable frame rate, huge bitrates. Generic wrappers often break
  these or produce washed-out output.
- "Never hand back a file that won't play" is a trust promise competitors do
  not make explicit.

## Target user

Primary: non-technical Windows and macOS users with phone or camera videos.
They will not install Python, edit a config, or read a codec guide. They may
not know what "HEVC" means. They expect a download button, a drag-and-drop
window, a progress bar, and a working file.

Secondary: the same person compressing a folder of clips at once.

Not the primary user in v1: video editors, encoding hobbyists, developers
wanting an API, Linux users (supported later), mobile-only users.

## Goals

1. **One action.** Drop video, choose a purpose, get a result. No mandatory
   advanced settings.
2. **Fit the need.** Purpose presets plus an exact "fit under N MB" mode.
3. **Guaranteed playable.** Verify output; automatic H.264 fallback if the
   chosen encode is not decodable/valid.
4. **Phone-video correct.** Handle rotation, anamorphic pixels, VFR, 10-bit,
   HEVC, HDR/Dolby Vision, and multiple audio tracks without artifacts or
   washed-out color.
5. **Local and private.** No network requests for compression; strip location
   metadata by default; no telemetry.
6. **No setup.** Bundle FFmpeg. Ship installers for Windows and macOS.
7. **Batch.** Queue multiple files/folders with per-file progress and cancel.
8. **Adoptable OSS.** Clear README, demo, releases, Homebrew/winget, tests,
   contributor docs.

## Non-goals (v1)

- Video editing, trimming, merging, subtitles editing.
- Pro controls (per-title encoding, custom filter graphs, codec zoo).
- Cloud/hosted service or user accounts.
- Mobile app.
- Linux build (planned after Win/macOS).
- Monetization, ads, upsells, watermarks.
- Automatic content analysis / AI upscaling.

## Anti-goals (failure even if it runs)

- Any compression path that uploads the user's video.
- Producing a file that silently fails to open on a normal phone or computer.
- Losing or overwriting the original file.
- Requiring the user to install Python, FFmpeg, or codecs.
- A confusing failure with no plain-language explanation or fallback.
- Shipping a huge installer that takes minutes to launch.
- Hardcoding platform size limits as permanent truth (limits change).

## User decisions (from the design conversation)

- Primary user: non-technical people shrinking phone/DSLR clips.
- Position: A, the no-upload phone-video shrinker.
- Success: adopted open-source project, not revenue.
- v1 delivery: one-click desktop app for Windows and macOS.
- Core UX: purpose presets plus exact "fit under N MB".
- Tech: keep the Python engine and wrap it.
- Timeline: roadmap only; no fixed deadline.

## Product behavior

### First run

- No account, no setup wizard. A single window with a large drop zone.
- A one-line privacy statement: "Videos never leave this computer."
- A short "How it works" link, not a tutorial wall.

### Compress flow

1. Drop one or more video files, or a folder.
2. Pick a purpose:
   - **Send to someone** — small, safe, good on any phone.
   - **Discord** — default 10 MB, editable.
   - **Email** — default 25 MB, editable.
   - **Save storage** — smallest watchable file.
   - **Custom size** — "fit under __ MB".
   - Presets are editable defaults, not claims about current platform limits.
3. Optional expandable "Options":
   - Speed: **Fast** (default for sharing), Balanced, Smallest.
   - Codec: **Automatic** (recommended), H.264 (compatibility), HEVC (smallest).
   - Keep HDR (off by default; see HDR policy).
   - Keep metadata (off by default; GPS/location stripped).
   - Output folder (default: next to the input).
   - Advanced/collapsed settings stay out of the main flow.
4. Press **Compress**. Show per-file progress, estimated time, and Cancel.
5. On success: original size, new size, percent saved, and buttons
   **Open file** / **Show in folder** / **Compress more**.
6. On failure: plain-language reason, what was tried, and a "Try
   compatibility mode" action.

### Output

- Default name: `<original-stem>-small.mp4`, with numeric suffix on collision.
- Default location: same folder as the source; if not writable, a user Videos
  folder (`~/Movies/NanoCompress` on macOS, `~/Videos/NanoCompress` on
  Windows).
- Never overwrite the source. Write to a temp file and rename on success.
- Show the output path and reveal it in the file manager.

### Batch

- Multiple files and folders can be queued.
- Process sequentially by default; allow concurrency 1–2 later.
- A failure on one file does not stop the queue.
- Per-file status and a final summary.

## Presets and encoding policy

Presets are product-level intents, not codec settings:

| Preset | Intent | Default target |
|---|---|---|
| Send to someone | **Fast**, safe, plays everywhere | ~3–5 MB/min at 720p, hardware/x264 |
| Discord | Fit a hard attachment limit | 10 MB total |
| Email | Fit a hard attachment limit | 25 MB total |
| Save storage | Smallest watchable, phone screen | x265 medium, 480p/720p |
| Custom size | User-provided limit | N MB total |

**Send defaults to Fast first:** hardware encoder if one works, otherwise
x264 `veryfast` at 720p. Users who want smaller files can switch the speed
control to Smallest. This is the settled speed/size default.

Implementation may map presets to CRF or target bitrate. The user never sees
CRF.

### Exact-size engine

- Compute total budget from target bytes and duration.
- **A size cap is a hard cap, not an average.** Aim for 95% of the cap so
  container overhead and encoder variance cannot push the file over.
- Reserve audio (AAC 64–96k per track) and container overhead.
- Encode video with two-pass or a bounded CRF/bitrate search.
- Verify the actual file size. If it exceeds the cap, retry with a reduced
  bitrate, up to 3 times. If it still exceeds the cap, fail with a clear
  message rather than delivering a file that will be rejected.
- Never exceed the requested cap. The UI promises "under N MB", not
  "approximately N MB".
- If the target is impossible at the requested resolution/audio, reduce
  resolution, fps, or audio and tell the user exactly what changed.
- Short or VFR clips are known hard cases; test them explicitly.

### Playback baseline

"Verified playable" means:

- Container MP4 with `+faststart`.
- H.264 High profile, `yuv420p`, 8-bit, AAC-LC audio, for "compatibility"
  and sharing presets.
- HEVC Main profile, `yuv420p`, 8-bit, AAC-LC, `hvc1` tag, only for "Save
  storage" or when the user explicitly chooses HEVC.
- Source timing preserved; no broken A/V sync; no zero-length or truncated
  output.
- Validation is done with the bundled `ffprobe` plus a decode check of the
  start, middle, and end of the output. Real-device labs are out of scope for
  v1; the H.264 path is the compatibility guarantee.

"Send/Discord/Email" therefore default to **H.264**, even though HEVC is
smaller, because the promise is "it plays." "Save storage" defaults to
**HEVC** because the promise is "as small as possible." The user can override
the codec in Options.

### Codec policy

- Automatic (default): H.264 for sharing presets, HEVC for Save storage.
- H.264: maximum compatibility, larger files.
- HEVC: smallest files, modern devices; a plain-language warning that very
  old Windows installs may need the HEVC extension.
- Fallback: H.264/AAC when verification fails, regardless of the chosen
  codec, with a notice in the result.
- No AV1 in v1 (playback and speed risk for non-technical users).
- Hardware encoders may be used for speed on sharing presets; exact-size mode
  prefers accuracy over speed.

### HDR policy

- Default output is **SDR BT.709** for every preset, because "plays by
  default" includes ordinary Windows laptops and older TVs.
- "Keep HDR" opt-in preserves HDR10/HLG as 10-bit HEVC with color metadata
  and `hvc1`.
- Dolby Vision sources are tone-mapped to SDR in v1. "Keep HDR" does not
  attempt to preserve Dolby Vision; the UI explains this.
- If a size cap and "Keep HDR" conflict, the **size cap wins** and the UI
  reports that HDR was disabled to meet it.
- Tone-mapping must fail loudly if the bundled FFmpeg lacks `zscale`; it must
  not silently produce washed-out or green/purple output.
- Golden-file tests cover color primaries, transfer, matrix, and pixel format.

### Metadata policy

- Strip GPS/location, device serial, and other identifying metadata by
  default.
- Rotation is applied to the picture, not left as metadata.
- "Keep metadata" opt-in preserves tags/chapters.
- Never strip audio tracks or text subtitles silently; warn if a stream
  cannot be stored in MP4.

### Already-small inputs

If the source is already at or below the target, or the best encode would be
no smaller than the source (`output >= input * 0.98`), do **not** create a
larger file. Return the original with an "already small enough" result and
explain it. The original is never overwritten.

### Frame rate and timing

- Preserve source timestamps by default; do not force CFR. Most phone clips
  are VFR and forcing CFR can cause sync drift or size surprises.
- "Compatibility mode" (advanced) may normalize to CFR at 30 fps (or the
  source average, whichever is lower) for stubborn players.
- Exact-size budgeting uses the source's average frame rate and duration;
  the output preserves timing unless compatibility mode is selected.
- Tests cover VFR phone-style clips and confirm duration is within 1 second
  of the source.

### Audio and subtitle contract

- Map the first video stream, all audio tracks, and all text subtitles.
- Audio is transcoded to AAC-LC; text subtitles to `mov_text`.
- Image-based subtitles (PGS/VobSub) cannot be stored in MP4: skip them with
  a per-stream warning, never fail the whole job.
- Never silently drop an audio track. If the size cap cannot be met while
  keeping every track, reduce bitrate/downmix first, then fail with a clear
  message that names the tracks and suggests a larger cap.
- If there is no audio, produce a video-only file without error.

## Performance budget and speed policy

Speed is a product feature, not an implementation detail. A non-technical user
will abandon an app that takes minutes for a one-minute clip.

Measured on a high-end laptop (i9-13900H, 14C/20T, Iris Xe), encoding a
60-second clip with a software encoder or Intel Quick Sync:

| Output | Setting | Speed | 60s clip takes |
|---|---|---|---|
| 1080p | x264 veryfast | 2.6x realtime | ~23 s |
| 1080p | x264 medium | 1.6x realtime | ~37 s |
| 1080p | x265 medium | 0.67x realtime | ~90 s |
| 1080p | x265 slow | 0.29x realtime | ~3.5 min |
| 1080p | HEVC hardware (QSV) | 5.0x realtime | ~12 s |
| 4K | x265 medium | 0.16x realtime | ~6 min |
| 4K | x265 slow | 0.08x realtime | ~12 min |
| 4K | HEVC hardware (QSV) | 1.4x realtime | ~43 s |
| 4K | H.264 hardware (QSV) | 1.7x realtime | ~36 s |

Caveat: this test upscaled a lower-resolution source, so software numbers are
optimistic; real 4K phone HEVC 10-bit footage decodes and encodes slower.
Average consumer laptops are also slower than this machine.

Policy:

- **Never default to x265 `slow` in the GUI.** It is a power-user setting.
- **Probe hardware encoders once at startup** with a tiny test encode; cache
  the result. Use VideoToolbox on macOS, NVENC/QSV/AMF on Windows, VAAPI on
  Linux.
- **Sharing presets use hardware when available**, otherwise x264
  `veryfast`/`faster` at 720p. This keeps a 1-minute clip under ~30 seconds on
  typical hardware.
- **Save storage uses x265 `medium` at 480p/720p**, not 4K, and may use
  hardware HEVC. Cap the source resolution before encoding to cut cost.
- **Exact-size mode uses two-pass**, roughly doubling encode time. Warn for
  clips longer than 10 minutes and offer a one-pass estimate instead.
- **Speed/size control:** Fast (hardware/x264 veryfast), Balanced (x265
  medium 720p), Smallest (x265 slow 720p, with a wait warning).
- **Background queue:** never block the UI; show progress and ETA; allow
  cancel; run at lower process priority to avoid fan noise and UI lag.
- **Acceptance budgets:** 1-min 1080p share ≤ 30 s on hardware, ≤ 90 s
  software; 1-min 4K share ≤ 60 s hardware, ≤ 3 min software after
  downscale; 1-min exact-size ≤ 3 min.
- **Thermal throttling:** sustained software x265 on laptops can lose 30–50%
  speed; hardware encoders are more stable. Benchmark on real target devices,
  not only the dev machine.

## Architecture

- **Engine (pure Python, no GUI imports):** the existing `nanocompress`
  package, extended with a stable `compress()` API, progress callbacks,
  cancellation, target-size logic, verification, and preset mapping.
- **CLI:** keep `compressor.py` for power users and tests; the GUI calls the
  same engine.
- **Desktop shell:** PySide6 (Qt) for v1. Rationale: one language, reuses the
  engine and tests, fastest path to a real app. The UI stays thin so a Tauri
  front end can replace it later if polish becomes the bottleneck.
- **Packaging:** PyInstaller or Nuitka, with pinned FFmpeg/ffprobe binaries
  bundled per platform. Build on GitHub Actions for Windows and macOS.
- **Threading:** encoding runs off the UI thread; progress parsed from
  `ffmpeg -progress`; cancel terminates the child process and removes the
  temp file.
- **No network:** no telemetry, no update check by default. Update checks can
  be added later as an explicit opt-in.
- **Licensing:** the app stays MIT. The bundled FFmpeg build and its codecs
  are distributed as separate executables with license notices and a source
  offer; this must be reviewed before release.

## Differentiators to ship

1. **Verified playable output** — ffprobe + decode checks, automatic H.264
   fallback.
2. **Exact-size that actually fits** — bounded retry, not a best-effort
   bitrate guess.
3. **Phone-video correctness** — HDR/Dolby Vision, rotation, 10-bit, VFR.
4. **Location metadata stripped by default** — privacy normal people
   understand.
5. **No upload, no ads, no watermark, no account** — stated plainly in the
   UI and README.
6. **Batch queue with plain-language results** — not a developer log.
7. **Local-only, free, open source** — auditable and trustworthy.

## Success metrics (adopted OSS, 12 months)

- A public v1 release for Windows and macOS.
- 500+ GitHub stars and 5,000+ downloads.
- 10+ external contributors or meaningful PRs.
- Issues answered within 7 days on average.
- Repeat usage signals from issues/discussions (no telemetry).
- A README/demo that lets a stranger succeed without asking for help.

## Risks

- **Installer trust:** unsigned Windows/macOS builds trigger warnings;
  signing/notarization costs money and time. Beta can ship unsigned with
  clear docs; plan signing before a broad launch.
- **FFmpeg licensing:** bundling a GPL build (libx264) creates obligations.
  Review before release; keep the app separate from the binary.
- **Installer size/startup:** Qt + FFmpeg can be large. Measure and optimize;
  consider Tauri later.
- **Target-size accuracy:** VFR, short clips, and multiple audio tracks are
  hard. Test a matrix and fail with a clear message.
- **HDR tone-mapping:** easy to get wrong. Add golden-file tests for color
  metadata and visual checks.
- **Crowded market:** the differentiation must be visible on the landing
  page, not buried in features.
- **Solo-maintainer scope creep:** ship a narrow v1, defer Linux/Tauri/AV1.
- **Preset staleness:** make limits editable and avoid promising platform
  policy.

## Phased roadmap

### Phase 0 — Design and positioning (this document)
Approve the position, target user, v1 scope, and non-goals.

### Phase 1 — Engine v3 (foundation)
Stable `compress()` API, target-size mode with retries, output verification +
H.264 fallback, metadata stripping, preset mapping, SDR/HDR policy, progress
callbacks, cancellation, batch planning, and tests for each.

### Phase 2 — Desktop MVP
PySide6 window: drop zone, preset picker, custom size, options, queue,
progress, cancel, results, error states, output handling.

### Phase 3 — Packaging and release
Bundle FFmpeg/ffprobe, icons, PyInstaller/Nuitka builds, GitHub Actions for
Windows/macOS, unsigned beta release with checksums, install/FAQ docs.
Then code signing and macOS notarization.

### Phase 4 — Differentiation polish
Playability verification UX, exact-size guarantee messaging, HDR-safe
output, metadata privacy toggle, before/after size summary, batch summary.

### Phase 5 — Adoption
README with GIF and one-line promise, demo video, comparison table, Homebrew
cask, winget manifest, issue templates, CONTRIBUTING, roadmap, Show HN and
relevant communities.

### Phase 6 — Later
Linux AppImage, Tauri UI if needed, hardware acceleration, folder watching,
localization, mobile companion, developer API.

## Builder check resolutions

A fresh reviewer read this document and raised six questions. They are
settled here so the implementation plan can proceed without guessing.

1. **Playback baseline.** "Verified playable" means MP4 + `+faststart`,
   H.264 High 8-bit SDR + AAC-LC for sharing presets, HEVC Main 8-bit SDR +
   AAC-LC + `hvc1` only for Save storage or explicit user choice. Validation
   is ffprobe plus decode checks at start/middle/end. H.264 is the
   compatibility guarantee; real-device labs are out of scope for v1.
2. **HDR / Dolby Vision.** All presets default to SDR BT.709. "Keep HDR"
   preserves HDR10/HLG only, as 10-bit HEVC. Dolby Vision is always
   tone-mapped to SDR in v1. If "Keep HDR" conflicts with a size cap, the
   cap wins and the UI explains why.
3. **Size cap semantics.** A cap is hard. Target 95% of the cap, retry up to
   3 times if over, and fail with a clear message rather than exceed it. The
   UI never says "approximately."
4. **VFR / frame rate.** Preserve source timestamps by default. Optional
   compatibility mode normalizes to CFR 30 (or lower source average). Budgets
   use average fps and duration. Duration must match within 1 second.
5. **Already-small inputs.** If the output would not be at least 2% smaller,
   return the original with an "already small enough" explanation. Never
   produce a larger file or overwrite the source.
6. **Stream contract.** Map the first video, all audio, and all text
   subtitles. Transcode audio to AAC-LC and text subs to `mov_text`. Skip
   image subtitles with a warning. Never silently drop audio; fail with a
   named explanation if the cap cannot be met with all tracks.

## What is left to the builder

- Confirm PySide6 vs Tauri for v1 (this document chooses PySide6).
- Visual design, branding, icon, and exact copy.
- Exact preset numbers and labels; how "Send" maps to CRF/resolution.
- Packaging tool choice (PyInstaller vs Nuitka) and installer format.
- Hardware-encoder scope and when to use it.
- Signing/notarization budget and timing.
- Exact target-size search parameters (two-pass vs CRF search) within the
  settled hard-cap, 95%-target, 3-retry rule.
- Supported OS versions (suggest Windows 10/11, macOS 12+).
- Default output folder behavior per OS.
- Whether v1 includes folder drop or only multi-file selection.
- Which FFmpeg build to bundle and the license review process.
