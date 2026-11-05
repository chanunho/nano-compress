# Contributing to NanoCompress

Thanks for helping improve NanoCompress. This project is a small, dependency-free Python CLI that wraps FFmpeg, so the bar for contributions is straightforward: keep it simple, keep it stdlib-only, and keep the tests green.

## Prerequisites

- Python 3.8 or newer
- `ffmpeg` and `ffprobe` on your `PATH` (with `libx264`, `libx265`, and `aac`; `zscale` for `--tonemap`)

## Development setup

```bash
git clone https://github.com/chanunho/nano-compress.git
cd nano-compress
python -m unittest discover -s tests -v
```

No `pip install` is required to run or test the project. You can still install it locally with `pip install .` if you want the `nanocompress` console command.

## Running the tests

```bash
python -m unittest discover -s tests -v
```

Integration tests generate short clips with FFmpeg and skip automatically when `ffmpeg`/`ffprobe` are missing. Please run the full suite before opening a pull request.

## Guidelines

- **Standard library only.** Do not add third-party runtime dependencies.
- **Never use `shell=True`.** Build FFmpeg argument lists and pass them to `subprocess`.
- **Keep the hard cap hard.** A `--target-size` result must never exceed the cap.
- **Never overwrite the source.** Write to a temp file and rename on success.
- **Preserve behavior.** Keep the legacy CLI path working when no product flag is used.
- **Add tests.** Bug fixes need a regression test; new behavior needs a focused test.
- **Match the style.** Follow the existing module layout and keep functions small and testable.
- **No secrets.** Never commit API keys, tokens, `.env` files, or `opencode.json`.

## Adding a preset or encoder

- Presets live in `nanocompress/presets.py`.
- Encoder discovery and selection live in `nanocompress/encoders.py`.
- Command construction lives in `nanocompress/command.py`.
- Orchestration and retry behavior lives in `nanocompress/compress.py`.

Update the README and tests whenever user-visible behavior changes.

## Pull requests

1. Fork the repository and create a branch from `main`.
2. Make the smallest change that solves the problem.
3. Run the full test suite.
4. Describe the change, the motivation, and any trade-offs in the pull request.

## Reporting bugs

Open an issue with:

- The command you ran
- FFmpeg version (`ffmpeg -version`)
- The source video's codec, resolution, duration, and whether it is HDR
- The full output and the error message

For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.
