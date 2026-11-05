# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 3.x | Yes |
| 2.x and older | No |

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability** (GitHub Security Advisories).

If that is unavailable, contact the maintainer through their GitHub profile and ask for a private channel.

Please include:

- A description of the issue and its impact
- Steps to reproduce
- The affected version/commit
- Any suggested fix

Do not include personal videos, credentials, or other sensitive data in a report. Use synthetic samples.

You can expect an initial response within a reasonable best-effort timeframe. This is a volunteer project, so no fixed SLA is promised.

## Scope and threat model

NanoCompress is designed to run entirely locally:

- It makes no network requests and has no telemetry, accounts, or uploads.
- It invokes `ffmpeg` and `ffprobe` as child processes with argument lists (never `shell=True`).
- It writes outputs to a temporary file and only renames on success.
- Input media is untrusted data. FFmpeg itself is a large native codebase; keep your FFmpeg build up to date.

Reports that are especially useful:

- Command injection or argument smuggling
- Path traversal or writing outside the requested output directory
- Overwriting the source or an unrelated file
- Leaking metadata/credentials by default
- Crashes or memory issues reachable from a malicious media file

## Secrets

This project must never contain credentials. `opencode.json` is ignored because it may contain local API keys; keep it out of the repository and rotate any key that was ever committed.
