"""
Cloudflare R2 Storage Service.

Handles all interactions with Cloudflare R2 (S3-compatible object storage)
for audio files and thumbnails. Falls back to local filesystem when R2
is not configured.
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional, Tuple

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError


class R2Storage:
    """Cloudflare R2 storage backend using S3-compatible API."""

    # Prefixes inside the bucket
    AUDIO_PREFIX = "audio/"
    THUMBNAIL_PREFIX = "thumbnails/"

    def __init__(self):
        self._client = None
        self._bucket = None
        self._public_url = None
        self._configured = False
        self._init()

    def _init(self):
        """Initialize R2 client from environment variables."""
        account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
        access_key = os.getenv("R2_ACCESS_KEY_ID", "").strip()
        secret_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
        self._bucket = os.getenv("R2_BUCKET_NAME", "").strip()
        self._public_url = os.getenv("R2_PUBLIC_URL", "").strip().rstrip("/")

        if not all([account_id, access_key, secret_key, self._bucket]):
            print("⚠️  R2 storage not configured — using local filesystem only.")
            return

        endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
            region_name="auto",
        )
        self._configured = True
        print(f"✅ R2 storage configured: bucket={self._bucket}")

    @property
    def is_configured(self) -> bool:
        return self._configured and self._client is not None

    # ─── Upload helpers ──────────────────────────────────────────────────────

    def _guess_content_type(self, filename: str) -> str:
        """Guess MIME type from filename extension."""
        mime, _ = mimetypes.guess_type(filename)
        if mime:
            return mime
        ext = os.path.splitext(filename)[1].lower()
        return {
            ".m4a": "audio/mp4",
            ".mp3": "audio/mpeg",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".opus": "audio/ogg",
            ".flac": "audio/flac",
            ".wav": "audio/wav",
            ".webm": "audio/webm",
            ".webp": "image/webp",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
        }.get(ext, "application/octet-stream")

    def upload_file(self, local_path: str, r2_key: str) -> bool:
        """
        Upload a local file to R2.

        Args:
            local_path: Absolute path to the local file.
            r2_key: Object key in the R2 bucket.

        Returns:
            True on success, False on failure.
        """
        if not self.is_configured:
            return False

        if not os.path.isfile(local_path):
            print(f"⚠️  R2 upload skipped — file not found: {local_path}")
            return False

        content_type = self._guess_content_type(local_path)

        try:
            self._client.upload_file(
                Filename=local_path,
                Bucket=self._bucket,
                Key=r2_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "CacheControl": "public, max-age=31536000, immutable",
                },
            )
            print(f"✅ R2 uploaded: {r2_key}")
            return True
        except ClientError as e:
            print(f"❌ R2 upload failed for {r2_key}: {e}")
            return False

    def upload_audio(self, local_path: str, filename: str) -> bool:
        """Upload an audio file to R2 under the audio/ prefix."""
        r2_key = f"{self.AUDIO_PREFIX}{filename}"
        return self.upload_file(local_path, r2_key)

    def upload_thumbnail(self, local_path: str, filename: str) -> bool:
        """Upload a thumbnail to R2 under the thumbnails/ prefix."""
        r2_key = f"{self.THUMBNAIL_PREFIX}{filename}"
        return self.upload_file(local_path, r2_key)

    # ─── URL helpers ─────────────────────────────────────────────────────────

    def get_audio_url(self, filename: str) -> Optional[str]:
        """Get the public URL for an audio file."""
        if not self.is_configured or not self._public_url:
            return None
        return f"{self._public_url}/{self.AUDIO_PREFIX}{filename}"

    def get_thumbnail_url(self, filename: str) -> Optional[str]:
        """Get the public URL for a thumbnail."""
        if not self.is_configured or not self._public_url:
            return None
        return f"{self._public_url}/{self.THUMBNAIL_PREFIX}{filename}"

    # ─── Presigned URL (fallback when no public URL is configured) ───────────

    def get_presigned_url(self, r2_key: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for private access."""
        if not self.is_configured:
            return None
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": r2_key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError:
            return None

    # ─── Check existence ─────────────────────────────────────────────────────

    def exists(self, r2_key: str) -> bool:
        """Check if an object exists in R2."""
        if not self.is_configured:
            return False
        try:
            self._client.head_object(Bucket=self._bucket, Key=r2_key)
            return True
        except ClientError:
            return False

    def audio_exists(self, filename: str) -> bool:
        return self.exists(f"{self.AUDIO_PREFIX}{filename}")

    def thumbnail_exists(self, filename: str) -> bool:
        return self.exists(f"{self.THUMBNAIL_PREFIX}{filename}")

    # ─── Delete ──────────────────────────────────────────────────────────────

    def delete(self, r2_key: str) -> bool:
        """Delete an object from R2."""
        if not self.is_configured:
            return False
        try:
            self._client.delete_object(Bucket=self._bucket, Key=r2_key)
            print(f"🗑️  R2 deleted: {r2_key}")
            return True
        except ClientError as e:
            print(f"❌ R2 delete failed for {r2_key}: {e}")
            return False

    def delete_audio(self, filename: str) -> bool:
        return self.delete(f"{self.AUDIO_PREFIX}{filename}")

    def delete_thumbnail(self, filename: str) -> bool:
        return self.delete(f"{self.THUMBNAIL_PREFIX}{filename}")

    # ─── Bulk upload (for migration) ─────────────────────────────────────────

    def bulk_upload_directory(self, local_dir: str, prefix: str) -> Tuple[int, int]:
        """
        Upload all files from a local directory to R2.

        Returns:
            (success_count, failure_count)
        """
        if not self.is_configured:
            return (0, 0)

        local_path = Path(local_dir)
        if not local_path.is_dir():
            return (0, 0)

        success = 0
        failed = 0

        for file_path in local_path.iterdir():
            if not file_path.is_file() or file_path.name.startswith("."):
                continue
            r2_key = f"{prefix}{file_path.name}"
            if self.upload_file(str(file_path), r2_key):
                success += 1
            else:
                failed += 1

        return (success, failed)


# Singleton instance
r2 = R2Storage()
