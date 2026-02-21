# Zora

Zora is a high-quality YouTube/YouTube Music audio downloader with:
- a modern Flask web app
- a CLI mode
- queue + playlist support
- library/history management with thumbnails
- dynamic storage configuration

## What You Get

- High-quality audio downloads via `yt-dlp` + `ffmpeg`
- Single track and playlist downloads
- Library view with play support
- Persistent history in SQLite
- Duplicate detection
- Dynamic download folder selection:
  - `ZORA_DOWNLOAD_DIR` env var
  - settings value (`download_dir`)
  - fallback `./downloads`

## Requirements

- Python 3.8+
- `ffmpeg` (required)
- Internet connection (for YouTube metadata/download)

Install `ffmpeg`:

- macOS (Homebrew):
  ```bash
  brew install ffmpeg
  ```
- Ubuntu/Debian:
  ```bash
  sudo apt update && sudo apt install -y ffmpeg
  ```
- Termux:
  ```bash
  pkg update && pkg install -y ffmpeg
  ```
- Windows (Chocolatey):
  ```powershell
  choco install ffmpeg
  ```

## Where To Run Commands

Run all setup/run commands from the project root (the folder that contains `run.py`).

Example:
```bash
cd /path/to/zora
```

## Installation

1. Create and activate virtual environment

- macOS/Linux:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```
- Windows (PowerShell):
  ```powershell
  python -m venv venv
  .\venv\Scripts\Activate.ps1
  ```

2. Install Python dependencies
```bash
pip install -r requirements.txt
```

## Run The Web App

Start server:
```bash
python run.py
```

Open:
```text
http://localhost:5001
```

Default bind:
- Host: `0.0.0.0`
- Port: `5001`

## Run The CLI

Basic:
```bash
python main.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Playlist:
```bash
python main.py "https://youtube.com/playlist?list=PLAYLIST_ID"
```

Custom format/quality/output:
```bash
python main.py "https://music.youtube.com/watch?v=VIDEO_ID" --format mp3 --quality 320 --output ./my-music
```

## Configuration

You can configure with environment variables and/or settings API/UI.

### Important Environment Variables

- `ZORA_HOST` (default: `0.0.0.0`)
- `ZORA_PORT` (default: `5001`)
- `ZORA_DOWNLOAD_DIR` (highest-priority download folder override)
- `SECRET_KEY`

Optional `.env` example:
```env
ZORA_HOST=0.0.0.0
ZORA_PORT=5001
ZORA_DOWNLOAD_DIR=/absolute/path/to/music
SECRET_KEY=change-this
```

### Download Folder Resolution (Priority)

1. `ZORA_DOWNLOAD_DIR` environment variable
2. Saved settings key `download_dir`
3. Default `./downloads`

## Data and Storage

- SQLite DB: `data.db`
- Downloaded audio: dynamic directory (see priority above)
- Thumbnails: `<download_dir>/thumbnails`

## API Endpoints (Core)

- `GET /api/settings`
- `POST /api/settings`
- `POST /api/info`
- `POST /api/download`
- `GET /api/status/<job_id>`
- `GET /api/history`
- `GET /play/<filename>`

## Project Structure

- `app/` - backend logic
  - `routes/` - API routes
  - `models/` - DB models
  - `services/` - queue/youtube services
- `docs/` - architecture and implementation specs
- `templates/` - HTML templates
- `static/` - JS/CSS/assets
- `run.py` - web app entry point
- `main.py` - CLI entry point
- `requirements.txt` - Python dependencies

## Planning Docs

- Auth + roles implementation spec: `docs/auth-rbac-spec.md`

## Troubleshooting

- `No module named yt_dlp` or Flask errors:
  - activate your venv
  - run `pip install -r requirements.txt`

- `FFmpeg not found`:
  - install `ffmpeg`
  - verify with `ffmpeg -version`

- App not reachable:
  - confirm `python run.py` is running
  - open `http://localhost:5001`
  - check port conflicts and firewall

- “Audio format not supported”:
  - keep default format as `m4a`
  - ensure `ffmpeg` is installed
  - refresh library via UI (history sync repairs stale mappings)

## Development Notes

- Bytecode check:
  ```bash
  python -m compileall app
  ```
- Backend tests:
  ```bash
  ./venv/bin/python -m pytest -q
  ```
- UI tests (Playwright):
  ```bash
  npm install
  npx playwright install chromium
  npm run test:ui
  ```
- Run all tests:
  ```bash
  npm run test:all
  ```

## License

MIT
