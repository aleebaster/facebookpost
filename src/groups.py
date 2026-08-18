"""
Facebook groups management.
Loads group URLs, validates them, and manages the list.
"""

from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from loguru import logger


class GroupManager:
    """Manages the list of Facebook groups to post in."""

    def __init__(self, groups_file: str = "data/groups.txt"):
        self.groups_file = groups_file
        self._groups: List[str] = []
        self._load()

    def _load(self):
        """Load groups from file."""
        self._groups = []
        path = Path(self.groups_file)

        if not path.exists():
            logger.warning(f"Groups file not found: {self.groups_file}")
            return

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue

                if self._is_valid_facebook_group_url(line):
                    self._groups.append(line)
                else:
                    logger.warning(f"Line {line_num}: Invalid Facebook group URL, skipping: {line}")

        logger.info(f"Loaded {len(self._groups)} group(s) from {self.groups_file}")

    def _is_valid_facebook_group_url(self, url: str) -> bool:
        """Validate that a URL is a valid Facebook group URL."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            if "facebook.com" not in parsed.netloc.lower():
                return False
            if "/groups/" not in parsed.path.lower():
                return False
            return True
        except Exception:
            return False

    def reload(self):
        """Reload groups from file."""
        self._load()

    @property
    def groups(self) -> List[str]:
        """Get the list of group URLs."""
        return list(self._groups)

    @property
    def count(self) -> int:
        """Get the number of groups."""
        return len(self._groups)

    def add_group(self, url: str) -> bool:
        """Add a group URL to the list and persist to file."""
        if not self._is_valid_facebook_group_url(url):
            logger.warning(f"Invalid Facebook group URL: {url}")
            return False

        if url in self._groups:
            logger.info(f"Group already in list: {url}")
            return False

        self._groups.append(url)

        # Append to file
        path = Path(self.groups_file)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"\n{url}")

        logger.info(f"Added group: {url}")
        return True

    def get_group_id(self, url: str) -> Optional[str]:
        """Extract the group ID from a URL."""
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == "groups":
                return parts[1]
        except Exception:
            pass
        return None

    def __iter__(self):
        return iter(self._groups)

    def __len__(self):
        return len(self._groups)

    def __getitem__(self, index):
        return self._groups[index]
