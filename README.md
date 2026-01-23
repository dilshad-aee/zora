# Zora - YouTube Music Downloader

Zora is a robust application designed to download high-quality audio from YouTube and YouTube Music. It offers both a modern web interface and a powerful command-line tool.

## Features

-   **High Quality Audio**: Downloads better quality audio than many other tools.
-   **Playlist Support**: Efficiently handles entire playlists.
-   **Queue System**: Queue manager for multiple downloads.
-   **History**: Tracks your download history.
-   **Metadata**: Automatically tags files with cover art, artist, and title.
-   **Dual Interface**: Use via Web UI or CLI.

## Prerequisites

-   Python 3.8 or higher
-   FFmpeg (required for audio conversion and metadata embedding)

## Installation

1.  **Clone the repository**

2.  **Install dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

### Web Interface
Start the web server:
```bash
python run.py
```
Then navigate to `http://localhost:5000` in your browser.

### Command Line Interface (CLI)
Download a track:
```bash
python main.py "https://music.youtube.com/watch?v=..."
```

Options:
-   `--format`: Choose format (mp3, m4a, flac, etc.)
-   `--quality`: Set bitrate (e.g., 320)
-   `--output`: Set output directory

```bash
python main.py "URL" --format mp3 --quality 320
```

## Project Structure

-   `app/`: Core application logic (routes, models, services)
-   `static/`: Frontend assets (JS, CSS)
-   `templates/`: HTML templates
-   `downloads/`: Default download location
-   `main.py`: CLI entry point
-   `run.py`: Web server entry point

## License
MIT
