"""
Tests for browser configuration.
Verifies correct Chrome profile paths and settings.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from src.browser import BrowserManager


def test_config_uses_profile_2():
    """Test that config.yaml specifies Profile 2."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    browser_config = config.get("browser", {})
    profile_name = browser_config.get("profile_name", "")
    assert profile_name == "Profile 2", f"Expected Profile 2, got: {profile_name}"
    print("PASS: config.yaml uses Profile 2")


def test_config_user_data_dir_not_profile():
    """Test that user_data_dir does not point to a profile subfolder."""
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    user_data_dir = config.get("browser", {}).get("user_data_dir", "")
    # user_data_dir should be the Chrome User Data root, not a profile folder
    assert "Profile" not in user_data_dir, (
        f"user_data_dir should not contain 'Profile': {user_data_dir}"
    )
    assert "User Data" in user_data_dir or not user_data_dir, (
        f"user_data_dir should point to Chrome User Data: {user_data_dir}"
    )
    print("PASS: user_data_dir does not point to profile subfolder")


def test_browser_manager_default_profile():
    """Test that BrowserManager defaults to Profile 2."""
    bm = BrowserManager()
    assert bm.profile_name == "Profile 2", f"Expected Profile 2, got: {bm.profile_name}"
    print("PASS: BrowserManager defaults to Profile 2")


def test_browser_manager_custom_profile():
    """Test that BrowserManager accepts custom profile."""
    bm = BrowserManager(profile_name="Profile 3")
    assert bm.profile_name == "Profile 3"
    print("PASS: BrowserManager accepts custom profile")


def test_find_chrome_executable():
    """Test that Chrome executable can be found."""
    path = BrowserManager._find_chrome_executable()
    if sys.platform == "win32":
        # On Windows, Chrome should be found
        assert path != "", "Chrome executable not found on Windows"
        assert Path(path).exists(), f"Chrome path does not exist: {path}"
        print(f"PASS: Chrome found at: {path}")
    else:
        print(f"PASS: Chrome search completed (path: {path or 'not found'})")


def test_default_user_data_dir():
    """Test that default user data directory is correct for the platform."""
    path = BrowserManager._get_default_user_data_dir()
    if sys.platform == "win32":
        assert "User Data" in path, f"Expected 'User Data' in path: {path}"
        assert "Google" in path, f"Expected 'Google' in path: {path}"
        print(f"PASS: Default user data dir: {path}")
    else:
        print(f"PASS: Default user data dir: {path}")


def test_no_disable_extensions():
    """Test that browser.py does not use --disable-extensions."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert "--disable-extensions" not in browser_py, (
        "browser.py should not contain --disable-extensions"
    )
    print("PASS: No --disable-extensions in browser.py")


def test_no_channel_chrome():
    """Test that browser.py does not use channel='chrome' (conflicts with executable_path)."""
    browser_py = Path("src/browser.py").read_text(encoding="utf-8")
    assert 'channel="chrome"' not in browser_py, (
        "browser.py should not use channel='chrome' with launch_persistent_context"
    )
    print("PASS: No channel='chrome' in browser.py")


if __name__ == "__main__":
    test_config_uses_profile_2()
    test_config_user_data_dir_not_profile()
    test_browser_manager_default_profile()
    test_browser_manager_custom_profile()
    test_find_chrome_executable()
    test_default_user_data_dir()
    test_no_disable_extensions()
    test_no_channel_chrome()
    print("\nAll browser config tests passed!")
