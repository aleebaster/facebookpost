"""
Media handling module.
Loads media URLs, validates formats, and manages media files.
"""

from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from loguru import logger


class MediaManager:
    """Manages photos and videos for property listings."""

    def __init__(
        self,
        photos_file: str = "data/photos.txt",
        videos_file: str = "data/videos.txt",
        allowed_photo_formats: Optional[List[str]] = None,
        allowed_video_formats: Optional[List[str]] = None,
    ):
        self.photos_file = photos_file
        self.videos_file = videos_file
        self.allowed_photo_formats = allowed_photo_formats or [".jpg", ".jpeg", ".png", ".webp"]
        self.allowed_video_formats = allowed_video_formats or [".mp4", ".mov", ".avi"]

        self._photos: List[str] = []
        self._videos: List[str] = []

        self._load_media()

    def _load_media(self):
        """Load photo and video URLs from files."""
        self._photos = self._load_urls(self.photos_file, "photo")
        self._videos = self._load_urls(self.videos_file, "video")

    def _load_urls(self, filepath: str, media_type: str) -> List[str]:
        """Load URLs from a file."""
        urls = []
        path = Path(filepath)

        if not path.exists():
            logger.warning(f"{media_type.capitalize()} file not found: {filepath}")
            return urls

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if self._is_valid_url(line):
                    urls.append(line)
                elif self._is_local_file(line):
                    urls.append(line)
                else:
                    logger.warning(f"Line {line_num}: Invalid {media_type} URL/path: {line}")

        logger.info(f"Loaded {len(urls)} {media_type}(s) from {filepath}")
        return urls

    def _is_valid_url(self, url: str) -> bool:
        """Check if string is a valid URL."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def _is_local_file(self, path: str) -> bool:
        """Check if string is a valid local file path."""
        return Path(path).exists()

    def validate_media(self, url: str) -> Tuple[bool, str]:
        """
        Validate a media URL/file.
        Returns (is_valid, error_message).
        """
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower() if parsed.path else ""

        # Check if it's a remote URL
        if parsed.scheme in ("http", "https"):
            # Check format
            if ext in self.allowed_photo_formats or ext in self.allowed_video_formats:
                # Check accessibility
                try:
                    with httpx.Client(timeout=10, follow_redirects=True) as client:
                        response = client.head(url)
                        if response.status_code == 200:
                            return True, ""
                        else:
                            return False, f"HTTP {response.status_code}"
                except Exception as e:
                    return False, f"Connection error: {e}"
            else:
                return False, f"Unsupported format: {ext}"

        # Check if it's a local file
        elif self._is_local_file(url):
            file_path = Path(url)
            if ext in self.allowed_photo_formats or ext in self.allowed_video_formats:
                return True, ""
            else:
                return False, f"Unsupported format: {ext}"

        else:
            return False, f"Not a valid URL or file: {url}"

    @property
    def photos(self) -> List[str]:
        """Get list of photo URLs/paths."""
        return list(self._photos)

    @property
    def videos(self) -> List[str]:
        """Get list of video URLs/paths."""
        return list(self._videos)

    @property
    def has_photos(self) -> bool:
        return len(self._photos) > 0

    @property
    def has_videos(self) -> bool:
        return len(self._videos) > 0

    def validate_all(self) -> List[Tuple[str, bool, str]]:
        """Validate all loaded media. Returns list of (url, is_valid, error)."""
        results = []
        for url in self._photos + self._videos:
            is_valid, error = self.validate_media(url)
            results.append((url, is_valid, error))
            if not is_valid:
                logger.warning(f"Media validation failed: {url} — {error}")
        return results

    def reload(self):
        """Reload media from files."""
        self._load_media()

    def __len__(self):
        return len(self._photos) + len(self._videos)

    def __iter__(self):
        """Iterate over all media."""
        for url in self._photos:
            yield url, "photo"
        for url in self._videos:
            yield url, "video"
