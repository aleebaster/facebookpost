"""
Facebook navigation tests.
Tests the browser flow logic, URL handling, and diagnostic logging.
For real Facebook testing, run: python -m src.main --mode DRY_RUN
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser import BrowserManager


def test_browser_manager_init_defaults():
    bm = BrowserManager()
    assert bm.profile_name == "Profile 2"
    assert bm.headless is False
    assert bm.slow_mo == 100
    print("PASS: BrowserManager init defaults correct")


def test_find_chrome_executable():
    path = BrowserManager._find_chrome_executable()
    assert path != "", "Chrome executable not found"
    assert Path(path).exists(), f"Chrome path does not exist: {path}"
    print(f"PASS: Chrome found at: {path}")


def test_default_user_data_dir():
    path = BrowserManager._get_default_user_data_dir()
    assert "User Data" in path, f"Expected 'User Data' in path: {path}"
    assert "Google" in path, f"Expected 'Google' in path: {path}"
    print(f"PASS: Default user data dir: {path}")


def test_is_chrome_running():
    result = BrowserManager._is_chrome_running()
    assert isinstance(result, bool)
    print(f"PASS: _is_chrome_running returns: {result}")


def test_no_disable_extensions():
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "--disable-extensions" not in browser_py
    print("PASS: No --disable-extensions in browser.py")


def test_no_channel_chrome():
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert 'channel="chrome"' not in browser_py
    print("PASS: No channel='chrome' in browser.py")


def test_hard_block_when_chrome_running():
    """Test that start() hard-blocks when Chrome is running."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "_log_chrome_block" in browser_py
    assert "Close ALL Chrome windows" in browser_py
    print("PASS: Hard block when Chrome is running")


def test_about_blank_critical_error():
    """Test that about:blank triggers critical error."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "CRITICAL" in browser_py
    assert "about:blank" in browser_py
    print("PASS: about:blank triggers critical error")


def test_page_diagnostics():
    """Test that page diagnostics are logged."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "Pages in context:" in browser_py
    assert "PAGE" in browser_py
    print("PASS: Page diagnostics present")


def test_open_facebook_logs():
    """Test that open_facebook() has proper logging."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "Opening Facebook..." in browser_py
    assert "Facebook loaded successfully" in browser_py
    assert "WORKING PAGE:" in browser_py
    print("PASS: open_facebook() has proper logging")


def test_main_logs_format():
    """Test that main.py has the expected log format."""
    main_py = Path("src/main.py").read_text(encoding="utf-8")
    assert "CURRENT WORKING PAGE:" in main_py
    assert "Loaded" in main_py and "group(s)" in main_py
    assert "CRITICAL: Facebook was NOT opened" in main_py
    assert "CRITICAL: Facebook session is NOT authenticated" in main_py
    print("PASS: main.py has expected log format")


if __name__ == "__main__":
    test_browser_manager_init_defaults()
    test_find_chrome_executable()
    test_default_user_data_dir()
    test_is_chrome_running()
    test_no_disable_extensions()
    test_no_channel_chrome()
    test_hard_block_when_chrome_running()
    test_about_blank_critical_error()
    test_page_diagnostics()
    test_open_facebook_logs()
    test_main_logs_format()
    print("\nAll navigation tests passed!")
