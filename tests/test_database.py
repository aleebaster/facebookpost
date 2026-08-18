"""
Tests for the database module.
"""

import os
import sys
import gc
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.database import PublicationLog, PublicationStatus


DB_PATH = "data/test_publications.db"


def cleanup():
    """Force cleanup of test database."""
    gc.collect()
    try:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
    except PermissionError:
        pass


def test_log_publication():
    """Test logging a publication entry."""
    cleanup()
    db = PublicationLog(DB_PATH)
    entry_id = db.log_publication(
        group_url="https://facebook.com/groups/test1",
        group_name="Test Group",
        status=PublicationStatus.SUCCESS.value,
        text_preview="Test post text",
    )
    assert entry_id > 0
    print("PASS: log_publication creates entry")
    cleanup()


def test_was_successful():
    """Test checking if a group was successfully published to."""
    cleanup()
    db = PublicationLog(DB_PATH)
    group_url = "https://facebook.com/groups/test2"
    assert not db.was_successful(group_url)

    db.log_publication(
        group_url=group_url,
        status=PublicationStatus.SUCCESS.value,
    )
    assert db.was_successful(group_url)
    print("PASS: was_successful works correctly")
    cleanup()


def test_get_all_publications():
    """Test getting all publication records."""
    cleanup()
    db = PublicationLog(DB_PATH)
    for i in range(3):
        db.log_publication(
            group_url=f"https://facebook.com/groups/test{i}",
            status=PublicationStatus.SUCCESS.value,
        )

    all_pubs = db.get_all_publications()
    assert len(all_pubs) == 3
    print("PASS: get_all_publications returns correct count")
    cleanup()


def test_get_stats():
    """Test getting publication statistics."""
    cleanup()
    db = PublicationLog(DB_PATH)
    db.log_publication(
        group_url="https://facebook.com/groups/s1",
        status=PublicationStatus.SUCCESS.value,
    )
    db.log_publication(
        group_url="https://facebook.com/groups/s2",
        status=PublicationStatus.FAILED.value,
    )

    stats = db.get_stats()
    assert stats["total"] == 2
    assert stats["SUCCESS"] == 1
    assert stats["FAILED"] == 1
    print("PASS: get_stats returns correct statistics")
    cleanup()


def test_has_successful_publication_today():
    """Test checking for today's successful publications."""
    cleanup()
    db = PublicationLog(DB_PATH)
    group_url = "https://facebook.com/groups/today"
    assert not db.has_successful_publication_today(group_url)

    db.log_publication(
        group_url=group_url,
        status=PublicationStatus.SUCCESS.value,
    )
    assert db.has_successful_publication_today(group_url)
    print("PASS: has_successful_publication_today works")
    cleanup()


def test_publication_status_enum():
    """Test that all status values are correct."""
    assert PublicationStatus.SUCCESS.value == "SUCCESS"
    assert PublicationStatus.FAILED.value == "FAILED"
    assert PublicationStatus.SKIPPED.value == "SKIPPED"
    assert PublicationStatus.REQUIRES_MANUAL_ACTION.value == "REQUIRES_MANUAL_ACTION"
    assert PublicationStatus.FACEBOOK_RESTRICTION.value == "FACEBOOK_RESTRICTION"
    print("PASS: PublicationStatus enum values are correct")


if __name__ == "__main__":
    test_log_publication()
    test_was_successful()
    test_get_all_publications()
    test_get_stats()
    test_has_successful_publication_today()
    test_publication_status_enum()
    cleanup()
    print("\nAll database tests passed!")
