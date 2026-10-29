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

HDR/wide-gamut sources are preserved as 10-bit HDR by default, because modern iPhones, Android devices, and Macs play it natively. Some Windows configurations may not, which is why the option to convert exists:

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
│   ├── probe.py             # ffprobe metadata parsing
│   ├── command.py           # FFmpeg command construction
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
