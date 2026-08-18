"""
Media handling module.
Loads media from local folders (data/photos/, data/videos/) and validates formats.
"""

from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from loguru import logger


class MediaManager:
    """Manages photos and videos for property listings."""

    def __init__(
        self,
        photos_file: str = "data/photos.txt",
        videos_file: str = "data/videos.txt",
        photos_dir: str = "data/photos",
        videos_dir: str = "data/videos",
        allowed_photo_formats: Optional[List[str]] = None,
        allowed_video_formats: Optional[List[str]] = None,
    ):
        self.photos_file = photos_file
        self.videos_file = videos_file
        self.photos_dir = Path(photos_dir)
        self.videos_dir = Path(videos_dir)
        self.allowed_photo_formats = allowed_photo_formats or [".jpg", ".jpeg", ".png", ".webp"]
        self.allowed_video_formats = allowed_video_formats or [".mp4", ".mov", ".webm"]

        self._photos: List[str] = []
        self._videos: List[str] = []

        self._load_media()

    def _load_media(self):
        """Load media from local folders and/or URL files."""
        self._photos = []
        self._videos = []

        # Load from local folders (primary method)
        self._photos.extend(self._load_from_dir(self.photos_dir, "photo"))
        self._videos.extend(self._load_from_dir(self.videos_dir, "video"))

        # Also load from URL files (legacy support)
        self._photos.extend(self._load_urls(self.photos_file, "photo"))
        self._videos.extend(self._load_urls(self.videos_file, "video"))

        # Deduplicate
        self._photos = list(dict.fromkeys(self._photos))
        self._videos = list(dict.fromkeys(self._videos))

    def _load_from_dir(self, directory: Path, media_type: str) -> List[str]:
        """Load media files from a local directory."""
        files = []

        if not directory.exists():
            logger.info(f"{media_type.capitalize()} directory not found: {directory}")
            logger.info(f"Create it and add {media_type} files there.")
            return files

        all_formats = self.allowed_photo_formats + self.allowed_video_formats

        for file_path in sorted(directory.iterdir()):
            if file_path.is_file() and not file_path.name.startswith("."):
                ext = file_path.suffix.lower()
                if ext in all_formats:
                    files.append(str(file_path.resolve()))
                else:
                    logger.warning(f"Skipping {media_type} file with unsupported format: {file_path.name}")

        if files:
            logger.info(f"Loaded {len(files)} {media_type}(s) from {directory}")

        return files

    def _load_urls(self, filepath: str, media_type: str) -> List[str]:
        """Load URLs from a text file (legacy support)."""
        urls = []
        path = Path(filepath)

        if not path.exists():
            return urls

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if self._is_valid_url(line):
                    urls.append(line)
                elif Path(line).exists():
                    urls.append(str(Path(line).resolve()))
                else:
                    logger.warning(f"Line {line_num}: Invalid {media_type} URL/path: {line}")

        if urls:
            logger.info(f"Loaded {len(urls)} {media_type}(s) from {filepath}")

        return urls

    def _is_valid_url(self, url: str) -> bool:
        """Check if string is a valid URL."""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def validate_media(self, filepath: str) -> Tuple[bool, str]:
        """
        Validate a media file.
        Returns (is_valid, error_message).
        """
        path = Path(filepath)

        if not path.exists():
            return False, f"File not found: {filepath}"

        ext = path.suffix.lower()

        if ext in self.allowed_photo_formats or ext in self.allowed_video_formats:
            # Check file size
            size_mb = path.stat().st_size / (1024 * 1024)
            if ext in self.allowed_photo_formats and size_mb > 10:
                return False, f"Photo too large: {size_mb:.1f} MB (max 10 MB)"
            if ext in self.allowed_video_formats and size_mb > 100:
                return False, f"Video too large: {size_mb:.1f} MB (max 100 MB)"
            return True, ""
        else:
            return False, f"Unsupported format: {ext}"

    @property
    def photos(self) -> List[str]:
        """Get list of photo file paths."""
        return list(self._photos)

    @property
    def videos(self) -> List[str]:
        """Get list of video file paths."""
        return list(self._videos)

    @property
    def has_photos(self) -> bool:
        return len(self._photos) > 0

    @property
    def has_videos(self) -> bool:
        return len(self._videos) > 0

    def validate_all(self) -> List[Tuple[str, bool, str]]:
        """Validate all loaded media. Returns list of (filepath, is_valid, error)."""
        results = []
        for filepath in self._photos + self._videos:
            is_valid, error = self.validate_media(filepath)
            results.append((filepath, is_valid, error))
            if not is_valid:
                logger.warning(f"Media validation failed: {filepath} -- {error}")
        return results

    def reload(self):
        """Reload media from folders and files."""
        self._load_media()

    def __len__(self):
        return len(self._photos) + len(self._videos)

    def __iter__(self):
        """Iterate over all media."""
        for path in self._photos:
            yield path, "photo"
        for path in self._videos:
            yield path, "video"
