#!/usr/bin/env python3
"""
Migrate local downloads and thumbnails to Cloudflare R2.

Usage:
    python migrate_to_r2.py                  # Upload all local files
    python migrate_to_r2.py --dry-run        # Preview what would be uploaded
    python migrate_to_r2.py --thumbnails     # Upload only thumbnails
    python migrate_to_r2.py --audio          # Upload only audio files

Requires R2 env vars to be set in .env (see .env.example).
"""

import os
import sys
import argparse
from pathlib import Path

# Load env vars before importing app modules
from dotenv import load_dotenv
load_dotenv()

from app.r2_storage import r2


AUDIO_EXTENSIONS = {'.m4a', '.mp3', '.aac', '.ogg', '.opus', '.flac', '.wav', '.webm', '.mka'}
IMAGE_EXTENSIONS = {'.webp', '.jpg', '.jpeg', '.png'}


def migrate_audio(download_dir: Path, dry_run: bool = False):
    """Upload all audio files from download directory to R2."""
    if not download_dir.exists():
        print(f"⚠️  Download directory not found: {download_dir}")
        return 0, 0

    audio_files = [
        f for f in download_dir.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS and not f.name.startswith('.')
    ]

    if not audio_files:
        print("📭 No audio files found to upload.")
        return 0, 0

    print(f"\n🎵 Found {len(audio_files)} audio file(s)")
    success = 0
    failed = 0

    for i, path in enumerate(sorted(audio_files), 1):
        size_mb = path.stat().st_size / (1024 * 1024)
        print(f"  [{i}/{len(audio_files)}] {path.name} ({size_mb:.1f} MB)", end="")

        if dry_run:
            print(" → SKIP (dry-run)")
            success += 1
            continue

        # Check if already exists in R2
        if r2.audio_exists(path.name):
            print(" → EXISTS (skipped)")
            success += 1
            continue

        if r2.upload_audio(str(path), path.name):
            print(" → ✅")
            success += 1
        else:
            print(" → ❌")
            failed += 1

    return success, failed


def migrate_thumbnails(thumbnails_dir: Path, dry_run: bool = False):
    """Upload all thumbnail files to R2."""
    if not thumbnails_dir.exists():
        print(f"⚠️  Thumbnails directory not found: {thumbnails_dir}")
        return 0, 0

    thumb_files = [
        f for f in thumbnails_dir.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS and not f.name.startswith('.')
    ]

    if not thumb_files:
        print("📭 No thumbnail files found to upload.")
        return 0, 0

    print(f"\n🖼️  Found {len(thumb_files)} thumbnail(s)")
    success = 0
    failed = 0

    for i, path in enumerate(sorted(thumb_files), 1):
        size_kb = path.stat().st_size / 1024
        print(f"  [{i}/{len(thumb_files)}] {path.name} ({size_kb:.0f} KB)", end="")

        if dry_run:
            print(" → SKIP (dry-run)")
            success += 1
            continue

        if r2.thumbnail_exists(path.name):
            print(" → EXISTS (skipped)")
            success += 1
            continue

        if r2.upload_thumbnail(str(path), path.name):
            print(" → ✅")
            success += 1
        else:
            print(" → ❌")
            failed += 1

    return success, failed


def main():
    parser = argparse.ArgumentParser(description="Migrate local files to Cloudflare R2")
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    parser.add_argument("--audio", action="store_true", help="Upload only audio files")
    parser.add_argument("--thumbnails", action="store_true", help="Upload only thumbnails")
    args = parser.parse_args()

    if not r2.is_configured:
        print("❌ R2 is not configured. Set R2_* env vars in .env first.")
        print("   See .env.example for required variables.")
        sys.exit(1)

    # Determine directories
    base_dir = Path(__file__).parent
    download_dir = base_dir / "downloads"
    thumbnails_dir = download_dir / "thumbnails"

    # Override from env
    env_dir = os.getenv("ZORA_DOWNLOAD_DIR", "").strip()
    if env_dir:
        download_dir = Path(env_dir)
        thumbnails_dir = download_dir / "thumbnails"

    upload_both = not args.audio and not args.thumbnails

    print("=" * 60)
    print("🚀 Zora → Cloudflare R2 Migration")
    if args.dry_run:
        print("   MODE: DRY RUN (no actual uploads)")
    print(f"   Audio dir:      {download_dir}")
    print(f"   Thumbnails dir: {thumbnails_dir}")
    print("=" * 60)

    total_success = 0
    total_failed = 0

    if upload_both or args.audio:
        s, f = migrate_audio(download_dir, dry_run=args.dry_run)
        total_success += s
        total_failed += f

    if upload_both or args.thumbnails:
        s, f = migrate_thumbnails(thumbnails_dir, dry_run=args.dry_run)
        total_success += s
        total_failed += f

    print("\n" + "=" * 60)
    print(f"✅ Uploaded: {total_success}")
    if total_failed:
        print(f"❌ Failed:   {total_failed}")
    print("=" * 60)

    if total_failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
