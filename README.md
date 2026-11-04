# NanoCompress 🎬📱

> An open-source video compression pipeline that produces the smallest practical MP4 at a resolution you choose, while staying playable by default on modern phones and computers.

---

## 🚀 Features

* **Smallest practical output:** Uses CRF-based encoding (not a fixed target size) to shrink each video as much as the chosen quality allows.
* **Resolution you control:** Pick the target height from 144p to 720p. Width is computed from the source display aspect ratio.
* **Plays by default:** Defaults to H.265/HEVC in MP4 with AAC audio, tagged `hvc1`, and writes `+faststart` so it starts instantly. H.264 is available as a maximum-compatibility fallback.
* **HDR aware:** HDR sources are preserved as 10-bit HDR by default; `--tonemap` converts them to SDR BT.709. H.264 + HDR automatically tone-maps to SDR.
* **Correct geometry:** Anamorphic sources get square pixels at the right display aspect ratio, and rotated phone videos are auto-rotated upright.
* **File or folder:** Compress one video, or point it at a folder to batch an entire library.
* **Phone-ready presets:** `--profile send|discord|email|storage` picks speed, resolution, codec, and any size cap for the way you plan to share the video. `--target-size` fits a strict MB budget.
* **Private by design:** Everything runs locally. There are no uploads, accounts, network calls, or telemetry.
* **Safe runs:** Writes a `.part.mp4` temp file and renames on success, skips existing outputs, and keeps going when one file in a batch fails.
* **No dependencies beyond FFmpeg:** Python standard library only.

---

## ⚙️ Prerequisites

1. **Python 3.8+**
2. **FFmpeg and ffprobe** with `libx265`, `libx264`, and `aac` support.
   * *Mac (Homebrew):* `brew install ffmpeg`
   * *Ubuntu/Debian:* `sudo apt update && sudo apt install ffmpeg`
   * *Windows (Chocolatey):* `choco install ffmpeg`

`--tonemap` also needs an FFmpeg build with `zscale`/`zimg` (the common Linux, macOS, and Windows builds include it).

---

## 📥 Installation

```bash
git clone https://github.com/your-username/nanocompress.git
cd nanocompress
```

No pip install is required.

---

## 🛠️ Usage

```bash
python compressor.py INPUT [OUTPUT] [options]
```

`INPUT` can be a video file or a folder.

### Single file

```bash
# Default: 240p, balanced quality, HEVC
python compressor.py movie.mp4

# Explicit output path
python compressor.py movie.mp4 movie_small.mp4 -r 240 -q small

# Smallest watchable file
python compressor.py movie.mp4 -r 240 -q small -p veryslow --denoise light

# Maximum compatibility (H.264)
python compressor.py movie.mp4 movie_h264.mp4 -r 360 -e h264 -q balanced
```

When `OUTPUT` is omitted, the result is written beside the input as `<name>_nc.mp4`.

### Folder / batch mode

```bash
# Compress every video directly inside the folder into ./compressed
python compressor.py /path/to/videos -r 240 -q balanced

# Include subfolders and mirror the folder tree into the output folder
python compressor.py /path/to/videos -r 240 --recursive

# Choose a different output folder
python compressor.py /path/to/videos /path/to/output -r 240
```

Existing outputs are skipped unless you pass `--overwrite`. A failure on one file is reported but does not stop the batch; the run exits non-zero if anything failed.

### Options

| Flag | Description | Default |
|---|---|---|
| `-r, --resolution` | Target height: `144,160,180,216,240,288,320,360,480,540,720` | `240` |
| `-q, --quality` | Named level: `small`, `balanced`, `quality` | `balanced` |
| `-c, --crf` | Raw CRF override `0-51` (wins over `--quality`) | none |
| `-e, --encoder` | `hevc` (smaller, modern devices) or `h264` (maximum compatibility) | `hevc` |
| `-p, --preset` | `ultrafast` … `veryslow`; slower is smaller | `slow` |
| `--fps` | Change framerate (keeps the original when omitted) | none |
| `--audio-bitrate` | AAC bitrate per audio track | `64k` |
| `--denoise` | `off`, `light`, `medium`, `strong` | `off` |
| `--10bit` | Encode 10-bit (HEVC only) | off |
| `--tonemap` | Convert HDR to SDR BT.709 | off |
| `--recursive` | Folder mode: include subfolders | off |
| `--overwrite` | Re-encode existing outputs | off |
| `--dry-run` | Print planned commands without encoding | off |
| `--version` | Print the version | — |

### Product presets

The product pipeline is enabled by `--profile` or `--target-size`. Presets choose a sensible speed, resolution, and codec for a common sharing destination:

| `--profile` | Speed | Target height | Codec | Size cap |
|---|---|---|---|---|
| `send` | fast | 720p | H.264 | none |
| `discord` | fast | 480p | H.264 | 10 MB |
| `email` | fast | 540p | H.264 | 25 MB |
| `storage` | balanced | 480p | HEVC | none |
| `custom` | fast | 720p | H.264 | required `--target-size` |

```bash
# Ready to send in a chat
python compressor.py phone.mov --profile send

# Fit a strict upload limit (MB, implies custom when no profile is given)
python compressor.py phone.mov --profile email --target-size 20

# Smaller storage copy with the balanced speed policy
python compressor.py phone.mov --profile storage
```

Product-pipeline flags:

| Flag | Description |
|---|---|
| `--profile` | `send`, `discord`, `email`, `storage`, or `custom` |
| `--target-size MB` | Output size cap in MB (float); implies `custom` when no profile is given |
| `--speed` | `fast`, `balanced`, or `smallest` |
| `--keep-hdr` | Preserve HDR10/HLG as 10-bit HDR instead of converting to SDR (use an HEVC preset such as `storage` for HEVC output) |
| `--keep-metadata` | Keep source metadata and chapters, including location tags |
| `--compatibility` | Force constant 30 fps for stubborn players |
| `--no-verify` | Skip post-encode verification |

The legacy flags (`-r/--resolution`, `-q/--quality`, `-c/--crf`, `-e/--encoder`, `-p/--preset`, `--fps`, `--audio-bitrate`, `--denoise`, `--10bit`, `--tonemap`, `--recursive`, `--overwrite`, `--dry-run`, `--version`) remain available when no product flag is used.

#### Hard size cap

When a preset or `--target-size` sets a cap, NanoCompress aims for about 95% of it, measures the actual output, and retries with a reduced bitrate for up to three attempts. If two attempts still miss, it drops the resolution. It never returns a file over the cap; if the target cannot be met it fails with a clear message.

#### Speed policy

* `fast` uses hardware encoders when available and safe (sharing presets without a hard cap and without `--keep-hdr`); otherwise it uses x264 `veryfast` or HEVC `fast`.
* `balanced` uses the `medium` preset.
* `smallest` always uses the slower software encoder presets.
* Hardware is never used for a hard size cap, and `smallest` is never hardware.

#### Verification and fallback

Each output is verified with ffprobe (duration and stream count) and decoded at the start, middle, and end. If verification fails, NanoCompress automatically retries with H.264. Use `--no-verify` to skip these checks.

#### Metadata, HDR, and timing

Metadata is stripped by default, including GPS/location tags; `--keep-metadata` preserves it. HDR is converted to SDR BT.709 by default, while `--keep-hdr` preserves HDR10/HLG as 10-bit HDR (HEVC with the `storage` preset). Dolby Vision is always tone-mapped to SDR in v1. Source timestamps are preserved by default; `--compatibility` forces constant 30 fps.

Outputs are named `<name>_nc.mp4` by default, and existing outputs are skipped unless `--overwrite` is passed. The product pipeline never overwrites the source, and it returns the original file if compression would not make it smaller. `--dry-run` prints the planned commands and a `planned` summary without encoding.

### Quality levels

| Level | HEVC CRF | H.264 CRF | Intent |
|---|---|---|---|
| `quality` | 24 | 21 | Cleaner, larger |
| `balanced` | 28 | 25 | Default; watchable on a phone |
| `small` | 32 | 29 | Smallest watchable |

Higher CRF means a smaller file and more visible artifacts. `--crf` overrides the table.

---

## 🎞️ What the pipeline does

1. **Probe** the source with ffprobe: duration, dimensions, sample aspect ratio, rotation, HDR, interlacing, audio tracks, subtitles.
2. **Build the filter chain**: optional HDR→SDR tone-map, optional deinterlace (`yadif`), optional denoise, Lanczos scale to the target height, square pixels (`setsar=1`), optional `fps`.
3. **Encode** with H.265 (`libx265`) or H.264 (`libx264`), AAC audio, `mov_text` subtitles, `hvc1` tag for HEVC, and `+faststart`.
4. **Preserve** all audio tracks and text subtitles. Image-based subtitles (PGS/VobSub) cannot be stored in MP4 and are skipped with a warning.
5. **Rename** the `.part.mp4` temp file to the final name only after a successful encode.

### HDR behavior

The legacy flags preserve HDR/wide-gamut sources as 10-bit HDR by default, because modern iPhones, Android devices, and Macs play it natively. The product pipeline (`--profile`/`--target-size`) instead converts HDR to SDR BT.709 by default; pass `--keep-hdr` there to preserve HDR10/HLG. Some Windows configurations may not play HDR, which is why the option to convert exists:

```bash
python compressor.py movie_hdr.mp4 movie_sdr.mp4 --tonemap
```

Using `-e h264` on an HDR source automatically tone-maps to SDR, because H.264 HDR is not reliably default-playable.

---

## 📂 Project Structure

```plaintext
nanocompress/
│
├── compressor.py            # CLI entry point
├── nanocompress/
│   ├── settings.py          # options, quality→CRF mapping, validation
│   ├── presets.py           # product presets and speed/codec resolution
│   ├── encoders.py          # encoder detection/selection and presets
│   ├── target_size.py       # size budget planning and retry math
│   ├── probe.py             # ffprobe metadata parsing
│   ├── command.py           # FFmpeg command construction
│   ├── process.py           # subprocess execution, progress, cancellation
│   ├── verify.py            # output duration/stream/decode verification
│   ├── compress.py          # product orchestration, retries, fallback
│   ├── jobs.py              # file/folder planning, naming, temp outputs
│   └── runner.py            # execution, size reporting, summaries
├── tests/                   # unittest suites (stdlib only)
├── README.md
└── LICENSE
```

---

## 🧪 Running the tests

```bash
python -m unittest discover -s tests -v
```

Integration tests generate short clips with FFmpeg and are skipped automatically if `ffmpeg`/`ffprobe` are missing.

---

## 🤝 Contributing

Contributions, feature requests, and bug reports are welcome.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
