# NanoCompress Unified Pipeline — Design

Date: 2026-10-29

## Intent and why

NanoCompress should be a "best in market" style compressor for everyday MP4
videos: it produces the **smallest practical file at a user-chosen
resolution** that still **plays by default** on modern phones (Android +
iPhone) and desktop computers — no extra apps, codec packs, or conversion.

The existing `compressor.py` is a basic single-file H.264 CRF downscaler. This
design replaces it with a single, focused pipeline that offers the best
compression-per-size that still meets the default-playback bar, with quality,
resolution, and batch behavior exposed to the user.

## Goals

- Smallest possible output at a user-selected resolution while remaining
  watchable on a phone screen.
- Output plays by simply opening it with the default player on modern iPhone,
  Android, and desktop OSes.
- User selects the resolution (no automatic resolution decisions).
- User selects quality via named levels and/or a raw CRF value.
- Handle either a single input file or a whole folder in one run.
- Preserve all audio tracks and subtitles that are compatible with MP4.
- Prefer good compression efficiency, but do not be needlessly slow.

## Non-goals

- Strict target file-size mode (e.g. "fit in exactly 200 MB").
- Automatic resolution selection based on content analysis.
- Exotic codecs or containers that require the viewer to install anything
  (no AV1-only, no MKV-only output).
- Editing, trimming, or re-timing content.
- A GUI. This is a CLI tool.

## Anti-goals (would mean failure even if it runs)

- Producing a file that silently fails to open on an iPhone or Android
  default player.
- Dropping audio tracks or subtitles when the user asked to preserve them,
  without clearly warning.
- Output whose duration or A/V sync differs from the source.
- Batch mode that crashes the whole run because one file is corrupt.

## Constraints

- Python 3.8+ standard library only; no third-party pip dependencies.
- Driven by FFmpeg/ffprobe. Must work on Linux, macOS, and Windows.
- Default codec family is H.265/HEVC in MP4 with AAC audio, because it is the
  smallest codec that modern phones and desktops play natively. H.264 is kept
  as an opt-in maximum-compatibility encoder.
- Must set `+faststart` so playback starts immediately in browsers/players.
- Must handle odd source dimensions and non-square sample aspect ratios.
- Must not require the source to be MP4 only (accept common formats ffmpeg
  can read), but outputs MP4.

## User-chosen decisions

- **Resolution:** the user chooses it; the pipeline never picks.
- **Quality:** named levels plus a raw CRF override.
- **Compatibility target:** H.265 (modern phones + desktop) by default, with
  H.264 available for maximum compatibility.
- **Audio/subtitles:** preserve all audio tracks and subtitles when possible.
- **Modes:** support both single-file and batch-folder from one command.
- **Time budget:** slow is acceptable, but avoid gratuitous slowness.

## Command-line interface

```
python compressor.py INPUT [OUTPUT] [options]
```

`INPUT` may be a file or a directory.

- File mode: `OUTPUT` is the output file path. If omitted, write next to the
  input with suffix `_nc.mp4`.
- Folder mode: `OUTPUT` is the output directory (default: `INPUT/compressed`).
  Every video file directly inside `INPUT` is processed (not recursive by
  default; `--recursive` opts in). Output names mirror input names with
  `_nc.mp4`.

Options:

| Flag | Meaning | Default |
|---|---|---|
| `-r, --resolution` | Target height in pixels; width auto, even, aspect preserved | `240` |
| `-q, --quality` | Named level: `small`, `balanced`, `quality` | `balanced` |
| `-c, --crf` | Raw CRF override (wins over `--quality`) | none |
| `-e, --encoder` | `hevc` (H.265) or `h264` | `hevc` |
| `-p, --preset` | Encoder preset | `slow` |
| `--fps` | Optional framerate override | keep original |
| `--audio-bitrate` | Per-track AAC bitrate | `64k` |
| `--denoise` | `off`, `light`, `medium`, `strong` | `off` |
| `--10bit` | Encode 10-bit (better gradients/compression) | off |
| `--tonemap` | Convert HDR sources to SDR (BT.709) | off |
| `--recursive` | Folder mode recurses into subfolders | off |
| `--overwrite` | Re-encode outputs that already exist | off |
| `--dry-run` | Print planned commands without encoding | off |

Validation:

- Resolution must be one of 144, 160, 180, 216, 240, 288, 320, 360, 480, 540,
  720.
- CRF must be within the encoder's valid range (0–51; practical guidance
  18–40).
- Quality level maps to a CRF per encoder (see below). `--crf` overrides it.
- Unknown or unreadable inputs fail with a clear message and non-zero exit.

## Codec and quality mapping

- Default encoder: `libx265`, MP4, AAC audio, `-tag:v hvc1` (needed for
  Apple/QuickTime recognition), `+faststart`.
- Optional encoder: `libx264`, MP4, AAC audio, `+faststart`.
- Both use `yuv420p` by default; `--10bit` selects `yuv420p10le` where
  supported (`libx265`). 10-bit is opt-in because it can reduce playback
  compatibility on older devices.
- x265 recommendation: keep `-tag:v hvc1`; do not force a level unless a
  compatibility problem is found in testing.

Named quality levels → CRF:

| Level | H.265 CRF | H.264 CRF | Intent |
|---|---|---|---|
| `quality` | 24 | 21 | Cleaner, larger |
| `balanced` | 28 | 25 | Default, watchable on phones |
| `small` | 32 | 29 | Smallest watchable |

Rationale: CRF values differ in meaning between encoders; the table keeps the
three levels roughly equivalent in perceived quality across codecs.

Optional denoise (applied before scaling) via `hqdn3d`:

- `off`: none
- `light`: `hqdn3d=1.5:1.5:6:6`
- `medium`: `hqdn3d=3:3:9:9`
- `strong`: `hqdn3d=6:6:12:12`

Denoise is most valuable for animation/grainy sources; it is off by default so
live-action detail is not softened unless the user opts in.

## HDR / wide-gamut handling

Detection: ffprobe reports a source as HDR when its transfer characteristic is
`smpte2084` (PQ/HDR10) or `arib-std-b67` (HLG), or its primaries are `bt2020`
with a non-SDR transfer. Wide gamut is treated the same way.

Default behavior — **preserve HDR**:

- Encode 10-bit (`yuv420p10le`) regardless of `--10bit`.
- Carry the source color metadata to the output (primaries, transfer, matrix,
  and any mastering/light-level side data that ffmpeg can pass through), so
  players recognize it as HDR.
- This is the default because modern iPhones, Android devices, and Macs play
  HDR HEVC/wide-gamut natively. Some Windows configurations may not; that is
  an accepted edge case, same as for HEVC generally.

`--tonemap` — convert HDR to SDR:

- Apply a tone-mapping filter chain to BT.709 SDR (e.g. `zscale` linearize →
  `tonemap` → `zscale` back to BT.709 → `yuv420p`), then encode 8-bit unless
  `--10bit` is also given.
- If the ffmpeg build lacks `zscale`, fail with a clear message telling the
  user to install a build with zimg, or use a system without the flag.

Interaction with `--encoder h264`:

- H.264 HDR is not reliably playable by default, so when the source is HDR and
  `--encoder h264` is selected, automatically tone-map to SDR and print a
  notice. The user does not have to pass `--tonemap` in this case.
- `--encoder h264 --10bit` is a validation error (10-bit H.264 is not
  default-playable on phones/desktops).

## Video filter chain

1. Detect rotation and interlacing (see below).
2. Optional HDR→SDR tone-mapping (only when `--tonemap`, or HDR + H.264).
3. Optional denoise (above).
4. Normalize to square pixels while preserving display aspect ratio, then
   scale to target height with Lanczos:
   `scale=-2:HEIGHT:flags=lanczos,setsar=1`
   - `-2` forces an even width; the display aspect is preserved.
   - If the source is smaller than the target height, still scale (upscaling
     is allowed so output matches the requested resolution; note this in
     output). (Builder may decide to skip upscaling only if it clearly
     conflicts with user expectations; default is to honor the request.)
5. Optional `fps=N`.

## Audio and subtitle handling

- Map all streams from the first input: `-map 0:v:0 -map 0:a? -map 0:s?`
  plus global metadata and chapters (`-map_metadata 0 -map_chapters 0`).
- Audio: transcode every audio track to AAC (`-c:a aac -b:a <audio-bitrate>`)
  for MP4 compatibility. Preserve channel layout by default (do not downmix);
  keep it simple and compatible.
- Subtitles: text subtitles are converted/copied to `mov_text` for MP4.
  - `-c:s mov_text` for text-based subtitles.
  - Image-based subtitles (PGS/VobSub) cannot be stored in MP4; skip them and
    print a clear warning per skipped stream. Never fail the whole job for
    this.
- If no audio stream exists, proceed video-only without error.

## Output and naming

- File mode default output: `<input-stem>_nc.mp4` beside the input.
- Folder mode default output dir: `<input-dir>/compressed`.
- Existing outputs are skipped unless `--overwrite`.
- Before encoding, refuse to overwrite the input file itself (compare resolved
  paths) unless the user explicitly supplies a different output.
- Use `-movflags +faststart` for every output.

## Progress, logging, and results

- Print a per-file header: name, source size, source duration/resolution.
- Stream ffmpeg progress to the terminal (do not swallow stderr).
- On success, print original size, output size, percentage saved, and output
  path.
- Folder mode prints a final summary table of all files, including skipped and
  failed ones, then exits non-zero if any file failed.

## Batch behavior and robustness

- Folder mode processes files sequentially (one encode at a time) to avoid
  memory/CPU thrash.
- A failure on one file is reported and does not stop the run.
- If a file already has an output and `--overwrite` is off, skip it and count
  it in the summary.
- `--dry-run` prints the commands that would run, with file sizes and planned
  CRF/resolution, and exits without encoding.
- Temporary/partial outputs: write to a `.part.mp4` temp name and rename on
  success, so interrupted runs never leave a broken file that looks valid.

## Verification (how the builder proves it works)

- Unit-level checks (no external media needed):
  - CLI parsing and quality→CRF mapping.
  - Folder discovery (recursive vs not), output naming, skip/overwrite logic.
  - Command construction for each encoder/quality/resolution combination.
- Integration checks with a short synthetic clip generated by ffmpeg:
  - Output opens with ffprobe; duration within ~1s of source.
  - Streams: video codec is hvc1 for HEVC / h264 for H.264; audio is AAC.
  - All source audio tracks present; text subtitles present as mov_text.
  - An anamorphic source is output with square pixels and the same display
    aspect ratio; a rotated source is not sideways.
  - An HDR source is preserved as 10-bit HDR by default; with `--tonemap` the
    output is 8-bit SDR BT.709.
  - `faststart` is present (`moov` before `mdat`).
  - Batch run over a temp folder produces one output per input and a summary.
  - A deliberately corrupt file in the batch is reported and does not stop the
    run.
- Manual check on the existing conan sample: `-r 240 -q small` must produce a
  smaller file than the current 147 MB H.264 output and still play.

## Builder's calls (settled during review)

- **SAR and rotation:** rely on ffmpeg's autorotation to apply rotation
  metadata, then normalize to square pixels with `setsar=1` while preserving
  the display aspect ratio. Do not preserve anamorphic signaling.
- **Recursive folder layout:** mirror the relative subdirectory tree under
  `OUTPUT`. Prune the output directory (default `INPUT/compressed`) from
  discovery so outputs are never re-encoded. Mirroring avoids collisions
  between same-named files in different subfolders. If two inputs in the same
  folder would produce the same name (e.g. `movie.mp4` and `movie.mkv`), append
  a numeric suffix to the later one.
- **`--10bit` + H.264:** validation error with a clear message (see HDR
  section).
- **Interlaced sources:** if ffprobe reports a field order other than
  `progressive`, apply `yadif` deinterlacing and print a notice. Progressive
  sources are never deinterlaced.
- **HDR + H.264:** auto tone-map to SDR with a notice (see HDR section).

## What is left to the builder

- Exact x265 parameter tuning (e.g. `aq-mode`, `psy-rd`, `sao`) as long as it
  does not reduce compatibility or contradict the quality mapping.
- The exact tone-mapping filter chain and metadata tagging details, provided
  the result is valid SDR BT.709.
- How progress is displayed and the precise wording of warnings/summaries.
- Directory traversal details (which extensions count as video).
- Whether to add a small `--list-encoders`/`--version` helper.
- Any Windows-specific quoting details.

## Assumptions

- "Default playback" means modern iOS/Android plus current desktop OSes, where
  HEVC in MP4 with AAC is supported. Older Windows without the HEVC extension
  is accepted as an edge case; H.264 remains available as the fallback.
- Users understand larger CRF = smaller file and more artifacts.
