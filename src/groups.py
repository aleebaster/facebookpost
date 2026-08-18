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

        logger.info(f"Groups file: {path.resolve()}")

        if not path.exists():
            logger.warning(f"Groups file not found: {self.groups_file}")
            return

        total_lines = 0
        comments = 0
        empty = 0
        invalid = 0

        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                total_lines += 1
                raw = line.rstrip("\n")
                line = line.strip()

                if not line:
                    empty += 1
                    continue
                if line.startswith("#"):
                    comments += 1
                    continue

                if self._is_valid_facebook_group_url(line):
                    self._groups.append(line)
                else:
                    invalid += 1
                    logger.warning(f"Line {line_num}: Invalid URL, skipping: {raw}")

        logger.info(f"Raw lines: {total_lines}")
        logger.info(f"Comments: {comments}")
        logger.info(f"Empty lines: {empty}")
        logger.info(f"Invalid URLs: {invalid}")
        logger.info(f"Valid group URLs: {len(self._groups)}")

        for idx, url in enumerate(self._groups, 1):
            logger.info(f"  [{idx}] {url}")

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
