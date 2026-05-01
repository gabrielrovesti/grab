# ⬇ grab

A personal music downloader — search any song, pick a version, choose where to save it. Runs as a native desktop window.

Built with FastAPI + yt-dlp on the backend, pywebview for the native window, and a minimal dark HTML/JS frontend. No Electron, no browser tab, no cloud dependency.

---

## Features

- **Live search** via YouTube Music — autocomplete as you type
- **Real download progress** — 0–100% bar fed directly from yt-dlp, with a conversion phase indicator
- **Native save dialog** — choose exactly where each file lands
- **Per-track bitrate** — 128 / 192 / 256 / 320 kbps, selectable per song
- **Single command to run** — no build step, no config

---

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI + yt-dlp + ytmusicapi |
| Audio extraction | ffmpeg via yt-dlp postprocessor |
| Desktop window | pywebview (Qt backend) |
| Frontend | Vanilla HTML/CSS/JS, IBM Plex Mono |

---

## Requirements

- Python 3.10+
- ffmpeg on PATH

```bash
# Windows (recommended)
winget install ffmpeg

# macOS
brew install ffmpeg

# Linux
apt install ffmpeg
```

---

## Installation

```bash
pip install fastapi uvicorn yt-dlp ytmusicapi PyQt6 PyQt6-WebEngine qtpy bottle proxy_tools
pip install pywebview --no-deps
```

---

## Usage

```bash
python run.py
```

Downloads are saved to the path you choose via the native dialog.  
Default fallback: `~/Music/grab/`

---

## Project Structure

```
grab/
├── main.py   # FastAPI app — search, suggest, download endpoints + embedded UI
└── run.py    # pywebview launcher — spins up uvicorn and opens the desktop window
```

---

## Notes

- Personal use only. Downloading copyrighted content may violate YouTube's ToS.
- Tested on Windows 10/11 with Python 3.12 and PyQt6 6.11.
- The pywebview Qt backend is required on Windows — `pythonnet` (the default WinForms backend) does not support Python 3.13+.
