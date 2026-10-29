# NanoCompress 🎬📱

> An open-source, ultra-efficient video compression pipeline designed to shrink MP4 videos down to their minimum size while keeping them fully playable on phones and computers with no extra setup.

---

## 🚀 Features

* **Universal Playback:** Uses H.264 (`libx264`) by default for maximum compatibility across phones, tablets, and computers.
* **Resolution Selection:** Choose your target resolution (144p up to 720p). Optimized for small screen viewing.
* **CRF-Based Compression:** Uses Constant Rate Factor (CRF) to minimize file size while maintaining consistent visual quality throughout.
* **Fast Start:** Outputs MP4 with `faststart` for instant playback in browsers and mobile players.
* **Cross-Platform:** Built with Python and driven by FFmpeg.

---

## ⚙️ Prerequisites

Before running NanoCompress, ensure you have the following installed on your system:

1. **Python 3.8+**
2. **FFmpeg** (Compiled with support for `libx264`/`libx265` and `aac`/`libopus`).
   * *Mac (Homebrew):* `brew install ffmpeg`
   * *Ubuntu/Debian:* `sudo apt update && sudo apt install ffmpeg`
   * *Windows (Chocolatey):* `choco install ffmpeg`

---

## 📥 Installation

Clone the repository and navigate into the project folder:

```bash
git clone https://github.com/your-username/nanocompress.git
cd nanocompress
```

---

## 🛠️ Usage

```bash
python compressor.py input.mp4 output.mp4 [options]
```

### Options

| Flag | Description | Default | Choices |
|---|---|---|---|
| `-r`, `--resolution` | Target height in pixels | `240` | `144`, `160`, `180`, `216`, `240`, `288`, `320`, `360`, `480`, `540`, `720` |
| `-c`, `--crf` | Quality (lower = larger/better, higher = smaller/worse) | `28` | `18-51` |
| `-p`, `--preset` | Encoding speed vs size (slower = smaller) | `medium` | `ultrafast` to `veryslow` |
| `-e`, `--encoder` | Video codec | `x264` | `x264`, `x265` |
| `--fps` | Change framerate (leave empty to keep original) | `None` | e.g., `24` |
| `--audio-bitrate` | Audio bitrate | `64k` | e.g., `48k`, `64k`, `96k` |

### Examples

```bash
# Compress to 240p with good balance (recommended for mobile)
python compressor.py movie.mp4 movie_240p.mp4 -r 240 -c 28

# Get smallest possible size at 240p
python compressor.py movie.mp4 movie_tiny.mp4 -r 240 -c 32 -p slow

# Maximum compatibility, slightly larger
python compressor.py movie.mp4 movie_compat.mp4 -r 240 -c 26

# Use x265 for smaller files (may have limited compatibility on very old devices)
python compressor.py movie.mp4 movie_x265.mp4 -r 240 -c 30 -e x265
```

---

## 📂 Project Structure

```plaintext
nanocompress/
│
├── compressor.py      # Core Python CLI pipeline script
├── README.md          # Project documentation
└── LICENSE            # Open-source license (e.g., MIT)
```

---

## 🤝 Contributing

Contributions, feature requests, and bug reports are welcome! Feel free to open an issue or submit a pull request.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See LICENSE for more information.
