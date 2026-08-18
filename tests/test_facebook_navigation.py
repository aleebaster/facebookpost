"""
Tests for Facebook navigation and browser configuration.
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBrowserConfig(unittest.TestCase):
    """Verify browser configuration points to the correct Chrome and profile."""

    def test_chrome_executable_exists(self):
        """System Chrome must exist at the expected path."""
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.assertTrue(
            Path(chrome_path).exists(),
            f"Chrome not found at: {chrome_path}",
        )

    def test_user_data_dir_exists(self):
        """Chrome User Data directory must exist."""
        user_data = r"C:\Users\andre\AppData\Local\Google\Chrome\User Data"
        self.assertTrue(
            Path(user_data).exists(),
            f"User Data not found: {user_data}",
        )

    def test_profile_2_exists(self):
        """Profile 2 must exist inside User Data."""
        profile_path = (
            r"C:\Users\andre\AppData\Local\Google\Chrome\User Data\Profile 2"
        )
        self.assertTrue(
            Path(profile_path).exists(),
            f"Profile 2 not found: {profile_path}",
        )

    def test_user_data_is_not_profile(self):
        """user_data_dir must be the root User Data, not a specific profile."""
        from src.browser import BrowserManager

        bm = BrowserManager()
        user_data = bm.user_data_dir or bm._get_default_user_data_dir()
        self.assertNotIn(
            "Profile",
            Path(user_data).name,
            "user_data_dir should be 'User Data', not a profile folder",
        )

    def test_profile_name_default(self):
        """Default profile should be Profile 2."""
        from src.browser import BrowserManager

        bm = BrowserManager()
        self.assertEqual(bm.profile_name, "Profile 2")

    def test_chrome_not_chromium(self):
        """Must use system Chrome, not Playwright Chromium."""
        from src.browser import BrowserManager

        bm = BrowserManager()
        executable = bm._find_chrome_executable()
        self.assertIn("chrome", executable.lower(), "Should use Chrome, not Chromium")
        self.assertNotIn("chromium", executable.lower(), "Should not use Chromium")

    def test_cdp_port_configured(self):
        """CDP port must be configured."""
        from src.browser import CDP_PORT

        self.assertEqual(CDP_PORT, 9222)

    def test_no_channel_chrome_in_args(self):
        """channel='chrome' must NOT be used with connect_over_cdp."""
        from src.browser import BrowserManager

        # Verify the start method uses connect_over_cdp, not launch_persistent_context
        import inspect

        source = inspect.getsource(BrowserManager.start)
        self.assertIn("connect_over_cdp", source, "Must use connect_over_cdp")
        self.assertNotIn(
            "launch_persistent_context", source, "Must not use launch_persistent_context"
        )


class TestChromeRunningDetection(unittest.TestCase):
    """Test Chrome process detection."""

    def test_is_chrome_running_returns_bool(self):
        """_is_chrome_running should return a boolean."""
        from src.browser import BrowserManager

        result = BrowserManager._is_chrome_running()
        self.assertIsInstance(result, bool)

    def test_no_disable_extensions(self):
        """--disable-extensions should NOT be in browser args."""
        from src.browser import BrowserManager

        bm = BrowserManager()
        # The start method should not use --disable-extensions
        import inspect

        source = inspect.getsource(BrowserManager.start)
        self.assertNotIn(
            "--disable-extensions",
            source,
            "--disable-extensions should not be used",
        )


class TestFacebookNavigation(unittest.TestCase):
    """Test navigation logic with mocked Playwright."""

    def test_open_facebook_checks_url(self):
        """open_facebook should verify the URL after navigation."""
        import inspect

        from src.browser import BrowserManager

        source = inspect.getsource(BrowserManager.open_facebook)
        self.assertIn("page.url", source, "Must check page.url")
        self.assertIn("about:blank", source, "Must check for about:blank")
        self.assertIn("facebook.com", source, "Must verify facebook.com in URL")

    def test_check_auth_checks_login_form(self):
        """check_facebook_auth should detect login forms."""
        import inspect

        from src.browser import BrowserManager

        source = inspect.getsource(BrowserManager.check_facebook_auth)
        self.assertIn("royal_login_button", source, "Must check for login button")
        self.assertIn("NOT AUTHENTICATED", source, "Must log NOT AUTHENTICATED")


if __name__ == "__main__":
    unittest.main()
