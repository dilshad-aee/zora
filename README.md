# 🎵 Zora

**A self-hosted music streaming app powered by YouTube.**

Zora lets you build your own personal music library and stream it from anywhere — with a modern web UI, playlists, lock screen controls, and more.

> **Try Zora live →** [www.zora.crackery.in](https://www.zora.crackery.in)

## Features

- 🎧 Stream high-quality audio in-browser with full playback controls
- 📱 Lock screen & notification controls (Media Session API)
- 🎨 Modern, responsive UI — works on desktop and mobile
- 📋 Playlist creation and management
- 🔀 Shuffle, repeat, sleep timer, gesture controls
- 🔍 Search YouTube directly from the app
- 📚 Persistent library with thumbnails and metadata
- 🔐 User authentication with role-based access (admin/user)
- 🧠 Smart duplicate detection
- ⚡ Range-request streaming for instant seek & low-latency playback
- 🌐 PWA support — installable on mobile
- 🖥️ CLI mode for bulk library management

## Requirements

- Python 3.8+
- `ffmpeg` (required)
- Internet connection (for YouTube metadata)

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

## Quick Start

Run all commands from the project root (the folder containing `run.py`).

1. **Create and activate virtual environment**

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

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Start the server**
   ```bash
   python run.py
   ```

4. **Open in your browser**
   ```
   http://localhost:5001
   ```

## Configuration

Configure via environment variables or the Admin Settings UI.

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ZORA_HOST` | `0.0.0.0` | Bind address |
| `ZORA_PORT` | `5001` | Server port |
| `ZORA_DOWNLOAD_DIR` | `./downloads` | Music storage directory |
| `ZORA_PLAYLIST_PREVIEW_LIMIT` | `120` | Max songs to preview from a YouTube playlist (20–500) |
| `SECRET_KEY` | auto-generated | Flask secret key |

Optional `.env` example:
```env
ZORA_HOST=0.0.0.0
ZORA_PORT=5001
ZORA_DOWNLOAD_DIR=/absolute/path/to/music
SECRET_KEY=change-this
```

### Music Storage Resolution (Priority)

1. `ZORA_DOWNLOAD_DIR` environment variable
2. Admin Settings → `download_dir`
3. Default `./downloads`

## Project Structure

```
app/            Backend logic
├── routes/     API routes
├── models/     Database models
├── services/   YouTube & queue services
templates/      HTML templates
static/         JS, CSS, assets
docs/           Architecture specs
run.py          Web app entry point
main.py         CLI entry point
```

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/settings` | Get app settings |
| `POST` | `/api/settings` | Update settings (admin) |
| `POST` | `/api/info` | Fetch YouTube metadata |
| `POST` | `/api/download` | Add music to library (admin) |
| `GET` | `/api/status/<job_id>` | Download job status |
| `GET` | `/api/history` | Get music library |
| `GET` | `/play/<filename>` | Stream audio |

## Troubleshooting

- **`No module named yt_dlp`** — activate your venv, then `pip install -r requirements.txt`
- **`FFmpeg not found`** — install ffmpeg, verify with `ffmpeg -version`
- **App not reachable** — confirm `python run.py` is running, check port `5001`
- **Audio won't play** — keep default format as `m4a`, ensure ffmpeg is installed

## Development

```bash
# Syntax check
python -m compileall app

# Backend tests
./venv/bin/python -m pytest -q

# UI tests (Playwright)
npm install && npx playwright install chromium
npm run test:ui

# All tests
npm run test:all
```

## License

MIT
