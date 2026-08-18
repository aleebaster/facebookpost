"""
Facebook navigation tests.
Tests the browser flow logic, URL handling, and diagnostic logging.
These are structural tests - they verify the code paths exist and are correct.
For real Facebook testing, run: python -m src.main --mode DRY_RUN
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser import BrowserManager


def test_browser_manager_init_defaults():
    """Test that BrowserManager initializes with correct defaults."""
    bm = BrowserManager()
    assert bm.profile_name == "Profile 2"
    assert bm.headless is False
    assert bm.slow_mo == 100
    print("PASS: BrowserManager init defaults correct")


def test_find_chrome_executable():
    """Test that Chrome executable can be found."""
    path = BrowserManager._find_chrome_executable()
    assert path != "", "Chrome executable not found"
    assert Path(path).exists(), f"Chrome path does not exist: {path}"
    print(f"PASS: Chrome found at: {path}")


def test_default_user_data_dir():
    """Test that default user data directory is correct."""
    path = BrowserManager._get_default_user_data_dir()
    assert "User Data" in path, f"Expected 'User Data' in path: {path}"
    assert "Google" in path, f"Expected 'Google' in path: {path}"
    print(f"PASS: Default user data dir: {path}")


def test_is_chrome_running():
    """Test that _is_chrome_running returns a boolean."""
    result = BrowserManager._is_chrome_running()
    assert isinstance(result, bool)
    print(f"PASS: _is_chrome_running returns: {result}")


def test_is_profile_locked_nonexistent():
    """Test that non-existent profile is not locked."""
    result = BrowserManager._is_profile_locked("/nonexistent/path", "Profile 999")
    assert result is False
    print("PASS: Non-existent profile is not locked")


def test_is_profile_locked_empty_lock():
    """Test that empty LOCK file is not considered a lock."""
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_dir = Path(tmpdir) / "TestProfile"
        profile_dir.mkdir()

        # Create empty LOCK file (like Chrome does on Windows)
        lock_file = profile_dir / "LOCK"
        lock_file.touch()  # 0 bytes

        result = BrowserManager._is_profile_locked(tmpdir, "TestProfile")
        assert result is False, "Empty LOCK file should not be considered a lock"
        print("PASS: Empty LOCK file is not a lock")


def test_is_profile_locked_singleton():
    """Test that SingletonLock IS considered a lock."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_dir = Path(tmpdir) / "TestProfile"
        profile_dir.mkdir()

        # Create SingletonLock file (Chrome creates this when profile is in use)
        lock_file = profile_dir / "SingletonLock"
        lock_file.write_text("lock")

        result = BrowserManager._is_profile_locked(tmpdir, "TestProfile")
        assert result is True, "SingletonLock should be considered a lock"
        print("PASS: SingletonLock is detected as lock")


def test_is_profile_locked_nonempty_lock():
    """Test that non-empty LOCK file IS considered a lock."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_dir = Path(tmpdir) / "TestProfile"
        profile_dir.mkdir()

        # Create non-empty LOCK file
        lock_file = profile_dir / "LOCK"
        lock_file.write_text("locked")

        result = BrowserManager._is_profile_locked(tmpdir, "TestProfile")
        assert result is True, "Non-empty LOCK file should be considered a lock"
        print("PASS: Non-empty LOCK file is detected as lock")


def test_no_disable_extensions():
    """Test that browser.py does not use --disable-extensions."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "--disable-extensions" not in browser_py
    print("PASS: No --disable-extensions in browser.py")


def test_no_channel_chrome():
    """Test that browser.py does not use channel='chrome'."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert 'channel="chrome"' not in browser_py
    print("PASS: No channel='chrome' in browser.py")


def test_diagnostic_logging_in_start():
    """Test that start() method contains diagnostic logging."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "Chrome process detected:" in browser_py
    assert "Profile 2 lock detected:" in browser_py
    assert "User data directory:" in browser_py
    print("PASS: Diagnostic logging present in start()")


def test_open_facebook_has_url_logging():
    """Test that open_facebook() logs URLs."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "Before navigation URL:" in browser_py
    assert "After navigation URL:" in browser_py
    assert "Page title:" in browser_py
    print("PASS: open_facebook() has URL logging")


def test_screenshot_on_failure():
    """Test that _save_debug_screenshot exists."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "_save_debug_screenshot" in browser_py
    assert "navigation_failure" in browser_py
    print("PASS: Debug screenshot on failure")


if __name__ == "__main__":
    test_browser_manager_init_defaults()
    test_find_chrome_executable()
    test_default_user_data_dir()
    test_is_chrome_running()
    test_is_profile_locked_nonexistent()
    test_is_profile_locked_empty_lock()
    test_is_profile_locked_singleton()
    test_is_profile_locked_nonempty_lock()
    test_no_disable_extensions()
    test_no_channel_chrome()
    test_diagnostic_logging_in_start()
    test_open_facebook_has_url_logging()
    test_screenshot_on_failure()
    print("\nAll navigation tests passed!")
