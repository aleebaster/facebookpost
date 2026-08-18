"""
Tests for Facebook navigation and browser configuration.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestBrowserConfig(unittest.TestCase):
    """Verify browser configuration points to the correct Chrome and profile."""

    def test_chrome_executable_exists(self):
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        self.assertTrue(Path(chrome_path).exists(), f"Chrome not found: {chrome_path}")

    def test_user_data_dir_exists(self):
        user_data = r"C:\Users\andre\AppData\Local\Google\Chrome\User Data"
        self.assertTrue(Path(user_data).exists(), f"User Data not found: {user_data}")

    def test_profile_2_exists(self):
        profile_path = r"C:\Users\andre\AppData\Local\Google\Chrome\User Data\Profile 2"
        self.assertTrue(Path(profile_path).exists(), f"Profile 2 not found: {profile_path}")

    def test_user_data_is_not_profile(self):
        from src.browser import BrowserManager
        bm = BrowserManager()
        user_data = bm.user_data_dir or bm._get_default_user_data_dir()
        self.assertNotIn("Profile", Path(user_data).name)

    def test_profile_name_default(self):
        from src.browser import BrowserManager
        bm = BrowserManager()
        self.assertEqual(bm.profile_name, "Profile 2")

    def test_chrome_not_chromium(self):
        from src.browser import BrowserManager
        bm = BrowserManager()
        executable = bm._find_chrome_executable()
        self.assertIn("chrome", executable.lower())
        self.assertNotIn("chromium", executable.lower())

    def test_cdp_port_configured(self):
        from src.browser import CDP_PORT
        self.assertEqual(CDP_PORT, 9222)

    def test_uses_connect_over_cdp(self):
        from src.browser import BrowserManager
        import inspect
        source = inspect.getsource(BrowserManager.start)
        self.assertIn("connect_over_cdp", source)
        self.assertNotIn("launch_persistent_context", source)

    def test_no_automation_controlled(self):
        from src.browser import BrowserManager
        import inspect
        source = inspect.getsource(BrowserManager.start)
        self.assertNotIn("AutomationControlled", source)
        self.assertNotIn("disable-blink-features", source)

    def test_uses_junction_not_copy(self):
        """Bot must use junction, not copy."""
        from src.browser import BrowserManager
        import inspect
        source = inspect.getsource(BrowserManager.start)
        self.assertIn("mklink", source, "Must use mklink /J for junction")
        self.assertNotIn("shutil.copytree", source, "Must NOT copy profile")
        self.assertNotIn("shutil.copy2", source, "Must NOT copy profile")

    def test_no_is_chrome_running(self):
        """_is_chrome_running must NOT exist."""
        from src.browser import BrowserManager
        self.assertFalse(hasattr(BrowserManager, "_is_chrome_running"))


class TestFacebookNavigation(unittest.TestCase):
    """Test navigation logic."""

    def test_open_facebook_checks_url(self):
        import inspect
        from src.browser import BrowserManager
        source = inspect.getsource(BrowserManager.open_facebook)
        self.assertIn("page.url", source)
        self.assertIn("about:blank", source)
        self.assertIn("facebook.com", source)

    def test_check_auth_checks_login_form(self):
        import inspect
        from src.browser import BrowserManager
        source = inspect.getsource(BrowserManager.check_facebook_auth)
        self.assertIn("royal_login_button", source)
        self.assertIn("NOT AUTHENTICATED", source)


if __name__ == "__main__":
    unittest.main()
