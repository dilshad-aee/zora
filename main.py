#!/usr/bin/env python3
"""
YouTube Music Download App - CLI Entry Point

Usage:
    python main.py <url>
    python main.py <url> --format mp3 --quality 320
    python main.py <url> --output ./my-music
    
Examples:
    python main.py "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    python main.py "https://youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"
"""

import sys
import argparse
from app import YTMusicDownloader
from app.exceptions import (
    DownloadError, 
    PlaylistError, 
    FFmpegError, 
    NetworkError,
    InvalidURLError
)
from app.utils import format_duration


def print_progress(info: dict):
    """Print download progress."""
    percent = info.get('percent_str', '0%')
    speed = info.get('speed', 0)
    speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed else "-- MB/s"
    eta = info.get('eta', 0)
    eta_str = format_duration(eta) if eta else "--:--"
    
    print(f"\r  Progress: {percent} | Speed: {speed_str} | ETA: {eta_str}", end='', flush=True)


def print_complete(info: dict):
    """Print completion message."""
    print(f"\n  ✓ Downloaded: {info.get('filename', 'file')}")


def main():
    parser = argparse.ArgumentParser(
        description='Download audio from YouTube/YouTube Music',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "https://www.youtube.com/watch?v=VIDEO_ID"
  %(prog)s "https://youtube.com/playlist?list=PLAYLIST_ID"
  %(prog)s "https://music.youtube.com/watch?v=VIDEO_ID" --format mp3
        """
    )
    
    parser.add_argument(
        'url',
        help='YouTube or YouTube Music URL (video or playlist)'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='./downloads',
        help='Output directory (default: ./downloads)'
    )
    
    parser.add_argument(
        '-f', '--format',
        choices=['m4a', 'mp3', 'opus', 'flac', 'wav', 'aac'],
        default='m4a',
        help='Audio format (default: m4a - best quality)'
    )
    
    parser.add_argument(
        '-q', '--quality',
        default='320',
        help='Audio quality/bitrate (default: 320)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output'
    )
    
    args = parser.parse_args()
    
    print(f"\n🎵 YouTube Music Downloader")
    print(f"=" * 40)
    print(f"URL: {args.url}")
    print(f"Format: {args.format.upper()} @ {args.quality}kbps")
    print(f"Output: {args.output}")
    print(f"=" * 40 + "\n")
    
    try:
        # Initialize downloader
        downloader = YTMusicDownloader(
            output_dir=args.output,
            audio_format=args.format,
            quality=args.quality,
            on_progress=None if args.quiet else print_progress,
            on_complete=None if args.quiet else print_complete,
            quiet=args.quiet
        )
        
        # Get info first
        print("📋 Fetching info...")
        info = downloader.get_info(args.url)
        
        if 'entries' in info:
            # Playlist
            entries = info.get('entries', [])
            print(f"📁 Playlist: {info.get('title', 'Unknown')}")
            print(f"   Tracks: {len(entries)}\n")
        else:
            # Single video
            print(f"🎵 Title: {info.get('title', 'Unknown')}")
            duration = info.get('duration')
            if duration:
                print(f"   Duration: {format_duration(duration)}")
            print()
        
        # Download
        print("⬇️  Downloading...")
        result = downloader.download(args.url)
        
        if result.get('success'):
            print(f"\n✅ Success!")
            
            if result.get('type') == 'playlist':
                print(f"   Downloaded: {result.get('downloaded', 0)}/{result.get('total', 0)} tracks")
                if result.get('failed', 0) > 0:
                    print(f"   ⚠️  Failed: {result.get('failed', 0)} tracks")
            else:
                print(f"   Title: {result.get('title', 'Unknown')}")
                
            print(f"   Location: {result.get('output_dir', args.output)}")
        else:
            print(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
            sys.exit(1)
            
    except InvalidURLError as e:
        print(f"\n❌ Invalid URL: {e.url}")
        print("   Please provide a valid YouTube or YouTube Music URL.")
        sys.exit(1)
        
    except FFmpegError as e:
        print(f"\n❌ FFmpeg Error:")
        print(f"   {e}")
        sys.exit(1)
        
    except NetworkError as e:
        print(f"\n❌ Network Error: {e}")
        print("   Try again later or use browser cookies.")
        sys.exit(1)
        
    except PlaylistError as e:
        print(f"\n❌ Playlist Error: {e}")
        if e.failed_items:
            print(f"   Failed items: {len(e.failed_items)}")
        sys.exit(1)
        
    except DownloadError as e:
        print(f"\n❌ Download Error: {e}")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Download cancelled by user.")
        sys.exit(130)
        
    except Exception as e:
        print(f"\n❌ Unexpected Error: {e}")
        sys.exit(1)
    
    print()


if __name__ == '__main__':
    main()
