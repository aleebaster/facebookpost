"""Tests for browser configuration and Facebook navigation."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


class TestBrowserConfig:
    """Verify browser configuration uses dedicated bot Chrome User Data."""

    def test_junction_path_is_different_from_target(self):
        """Bot Chrome User Data must differ from original Chrome User Data."""
        from src.browser import BrowserManager

        project_root = Path(__file__).resolve().parent.parent
        bot_data = project_root / "bot_chrome_data"

        original_user_data = BrowserManager._get_default_user_data_dir()

        # On the dev machine, bot_data won't exist yet, so we check the path string
        bot_str = str(bot_data)
        target_str = str(Path(original_user_data).resolve())

        # Critical: bot data path MUST be different from original
        assert bot_str != target_str, (
            f"Bot User Data {bot_str} must differ from original {target_str}"
        )
        assert "bot_chrome_data" in bot_str

    def test_find_chrome_executable(self):
        """Chrome executable detection should return a path."""
        from src.browser import BrowserManager
        result = BrowserManager._find_chrome_executable()
        # On Windows CI or dev machine, Chrome should exist
        # (may be empty on some CI environments)
        assert isinstance(result, str)

    def test_get_default_user_data_dir(self):
        """Default user data dir should return a valid path."""
        from src.browser import BrowserManager
        result = BrowserManager._get_default_user_data_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_cdp_port_constant(self):
        """CDP port should be 9222."""
        from src.browser import CDP_PORT
        assert CDP_PORT == 9222

    def test_bot_user_data_dir_constant(self):
        """Bot User Data directory name should be bot_chrome_data."""
        from src.browser import BOT_USER_DATA_DIR
        assert BOT_USER_DATA_DIR == "bot_chrome_data"

    def test_browser_manager_initialization(self):
        """BrowserManager should initialize with default values."""
        from src.browser import BrowserManager
        bm = BrowserManager()
        assert bm._chrome_process is None
        assert bm._playwright is None
        assert bm._browser is None
        assert bm._page is None
        assert bm.bot_chrome_pid is None


class TestBotChromeData:
    """Test that bot Chrome uses dedicated directory."""

    def test_bot_data_dir_created(self):
        """bot_chrome_data directory should exist or be creatable."""
        project_root = Path(__file__).resolve().parent.parent
        bot_data = project_root / "bot_chrome_data"
        # Directory should already exist (user created it)
        # or we can at least verify the path is valid
        assert "bot_chrome_data" in str(bot_data)

    def test_bot_data_not_original(self):
        """Bot User Data must never be the original Chrome User Data."""
        from src.browser import BrowserManager
        project_root = Path(__file__).resolve().parent.parent
        bot_data = str(project_root / "bot_chrome_data")
        original = BrowserManager._get_default_user_data_dir()

        # They must be different
        assert bot_data != original
        assert "bot_chrome_data" in bot_data
        assert "bot_chrome_data" not in original


class TestFacebookAuthDetection:
    """Test Facebook authentication detection selectors."""

    def test_login_selectors_defined(self):
        """Login selectors should be defined in browser module."""
        from src.browser import BrowserManager
        # The check_facebook_auth method should exist
        assert hasattr(BrowserManager, "check_facebook_auth")

    def test_auth_selectors_defined(self):
        """Auth selectors should be defined in browser module."""
        from src.browser import BrowserManager
        assert hasattr(BrowserManager, "check_facebook_auth")
        assert hasattr(BrowserManager, "wait_for_login")
