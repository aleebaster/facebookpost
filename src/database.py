"""
Publication log database module.
Tracks all publication attempts and results using SQLite.
"""

import sqlite3
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from loguru import logger


class PublicationStatus(Enum):
    """Possible publication statuses."""
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    REQUIRES_MANUAL_ACTION = "REQUIRES_MANUAL_ACTION"
    FACEBOOK_RESTRICTION = "FACEBOOK_RESTRICTION"


class PublicationLog:
    """SQLite-based publication log."""

    def __init__(self, db_path: str = "data/publications.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS publications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_url TEXT NOT NULL,
                    group_name TEXT,
                    timestamp TEXT NOT NULL,
                    text_variation_index INTEGER,
                    text_preview TEXT,
                    photos_used TEXT,
                    video_used INTEGER DEFAULT 0,
                    status TEXT NOT NULL,
                    post_url TEXT,
                    error_message TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_publications_group_url
                ON publications(group_url)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_publications_status
                ON publications(status)
            """)
            conn.commit()

        logger.debug(f"Database initialized at {self.db_path}")

    def log_publication(
        self,
        group_url: str,
        group_name: Optional[str] = None,
        text_variation_index: int = 0,
        text_preview: str = "",
        photos_used: Optional[List[str]] = None,
        video_used: bool = False,
        status: str = "SUCCESS",
        post_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> int:
        """Log a publication attempt. Returns the log entry ID."""
        photos_str = ",".join(photos_used) if photos_used else ""

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO publications
                    (group_url, group_name, timestamp, text_variation_index,
                     text_preview, photos_used, video_used, status, post_url, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_url,
                    group_name or "",
                    datetime.now().isoformat(),
                    text_variation_index,
                    text_preview[:500],
                    photos_str,
                    1 if video_used else 0,
                    status,
                    post_url or "",
                    error_message or "",
                ),
            )
            conn.commit()
            entry_id = cursor.lastrowid
            logger.debug(f"Logged publication #{entry_id}: {status} for {group_url}")
            return entry_id

    def was_successful(self, group_url: str) -> bool:
        """Check if the group was successfully published to."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM publications WHERE group_url = ? AND status = 'SUCCESS'",
                (group_url,),
            )
            count = cursor.fetchone()[0]
            return count > 0

    def get_last_status(self, group_url: str) -> Optional[str]:
        """Get the last publication status for a group."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT status FROM publications
                   WHERE group_url = ?
                   ORDER BY timestamp DESC LIMIT 1""",
                (group_url,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_all_publications(self) -> List[Dict]:
        """Get all publication records."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM publications ORDER BY timestamp DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_publications_by_status(self, status: str) -> List[Dict]:
        """Get all publications with a specific status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM publications WHERE status = ? ORDER BY timestamp DESC",
                (status,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_group_history(self, group_url: str) -> List[Dict]:
        """Get publication history for a specific group."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT * FROM publications
                   WHERE group_url = ?
                   ORDER BY timestamp DESC""",
                (group_url,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict:
        """Get publication statistics."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT status, COUNT(*) FROM publications GROUP BY status"
            )
            stats = {row[0]: row[1] for row in cursor.fetchall()}

            cursor = conn.execute("SELECT COUNT(*) FROM publications")
            stats["total"] = cursor.fetchone()[0]

            return stats

    def has_successful_publication_today(self, group_url: str) -> bool:
        """Check if there was a successful publication today for this group."""
        today = datetime.now().strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) FROM publications
                   WHERE group_url = ? AND status = 'SUCCESS'
                   AND timestamp LIKE ?""",
                (group_url, f"{today}%"),
            )
            count = cursor.fetchone()[0]
            return count > 0

    def clear_log(self):
        """Clear all publication records (use with caution)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM publications")
            conn.commit()
        logger.warning("Publication log cleared")
