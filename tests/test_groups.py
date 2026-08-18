"""
Tests for the group manager module.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.groups import GroupManager


def test_load_valid_groups():
    """Test loading valid group URLs from file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://www.facebook.com/groups/123456789\n")
        f.write("https://www.facebook.com/groups/realestate\n")
        f.write("# This is a comment\n")
        f.write("\n")  # empty line
        f.write("https://www.facebook.com/groups/987654321\n")
        temp_path = f.name

    try:
        gm = GroupManager(temp_path)
        assert gm.count == 3
        print("PASS: load_valid_groups: correct count")
    finally:
        os.remove(temp_path)


def test_invalid_urls_skipped():
    """Test that invalid URLs are skipped."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://www.facebook.com/groups/123\n")
        f.write("https://google.com\n")
        f.write("not a url at all\n")
        f.write("https://www.facebook.com/groups/456\n")
        temp_path = f.name

    try:
        gm = GroupManager(temp_path)
        assert gm.count == 2
        print("PASS: invalid_urls_skipped: correct count")
    finally:
        os.remove(temp_path)


def test_group_iteration():
    """Test iterating over groups."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://www.facebook.com/groups/111\n")
        f.write("https://www.facebook.com/groups/222\n")
        temp_path = f.name

    try:
        gm = GroupManager(temp_path)
        urls = list(gm)
        assert len(urls) == 2
        assert "111" in urls[0]
        print("PASS: group_iteration: works correctly")
    finally:
        os.remove(temp_path)


def test_group_indexing():
    """Test indexing into the group list."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://www.facebook.com/groups/aaa\n")
        f.write("https://www.facebook.com/groups/bbb\n")
        temp_path = f.name

    try:
        gm = GroupManager(temp_path)
        assert gm[0] == "https://www.facebook.com/groups/aaa"
        assert gm[1] == "https://www.facebook.com/groups/bbb"
        print("PASS: group_indexing: works correctly")
    finally:
        os.remove(temp_path)


def test_missing_file():
    """Test handling of missing file."""
    gm = GroupManager("nonexistent_file.txt")
    assert gm.count == 0
    print("PASS: missing_file: returns empty list")


def test_add_group():
    """Test adding a new group."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("https://www.facebook.com/groups/existing\n")
        temp_path = f.name

    try:
        gm = GroupManager(temp_path)
        initial_count = gm.count

        added = gm.add_group("https://www.facebook.com/groups/newgroup")
        assert added is True
        assert gm.count == initial_count + 1

        added2 = gm.add_group("https://www.facebook.com/groups/newgroup")
        assert added2 is False

        added3 = gm.add_group("https://google.com")
        assert added3 is False

        print("PASS: add_group: works correctly")
    finally:
        os.remove(temp_path)


if __name__ == "__main__":
    test_load_valid_groups()
    test_invalid_urls_skipped()
    test_group_iteration()
    test_group_indexing()
    test_missing_file()
    test_add_group()
    print("\nAll group manager tests passed!")
