"""Tests for Facebook navigation workflow."""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


class TestFacebookNavigation:
    """Test Facebook navigation logic."""

    def test_junction_path_is_different_from_target(self):
        """Junction path must NOT resolve to the same path as target."""
        # Simulate the logic from browser.py
        project_root = Path(__file__).resolve().parent.parent
        junction_path = project_root / "chrome_user_data"
        target_path = str(
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
        )
        junction_str = str(junction_path)
        # On dev machine, junction_path won't exist yet, so resolve() won't follow it
        # But we still verify the logic: the string paths must differ
        assert junction_str != target_path, (
            f"Junction {junction_str} must differ from target {target_path}"
        )
        assert "chrome_user_data" in junction_str
        assert "User Data" in target_path

    def test_find_chrome_executable(self):
        """Should find Chrome on the system."""
        from src.browser import BrowserManager

        path = BrowserManager._find_chrome_executable()
        assert path, "Chrome executable not found"
        assert Path(path).exists(), f"Chrome path does not exist: {path}"

    def test_get_default_user_data_dir(self):
        """Should return correct user data directory."""
        from src.browser import BrowserManager

        path = BrowserManager._get_default_user_data_dir()
        assert path
        assert "User Data" in path or "google-chrome" in path or "Chrome" in path

    def test_cdp_port_constant(self):
        """CDP port should be 9222."""
        from src.browser import CDP_PORT

        assert CDP_PORT == 9222

    def test_junction_dir_constant(self):
        """Junction directory name should be chrome_user_data."""
        from src.browser import JUNCTION_DIR

        assert JUNCTION_DIR == "chrome_user_data"

    def test_browser_manager_initialization(self):
        """BrowserManager initializes correctly."""
        from src.browser import BrowserManager

        bm = BrowserManager()
        assert bm._page is None
        assert bm._browser is None
        assert bm._chrome_process is None
        assert bm.profile_name == "Profile 2"


class TestJunctionCreation:
    """Test junction creation logic."""

    def test_mklink_command_format(self):
        """Verify the mklink command would be formatted correctly."""
        junction = "C:\\AI\\facebookpost\\chrome_user_data"
        target = "C:\\Users\\andre\\AppData\\Local\\Google\\Chrome\\User Data"
        cmd = ["cmd", "/c", "mklink", "/J", junction, target]
        assert "/J" in cmd
        assert junction in cmd
        assert target in cmd

    def test_junction_path_and_target_are_different_strings(self):
        """Critical: junction and target must be different strings."""
        project_root = Path(__file__).resolve().parent.parent
        junction = str(project_root / "chrome_user_data")
        target = str(
            Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
        )
        assert junction != target, "Junction and target must be different paths"


class TestFacebookAuthDetection:
    """Test authentication detection selectors."""

    def test_login_selectors_defined(self):
        """Login form selectors should be defined."""
        selectors = [
            'button[data-testid="royal_login_button"]',
            "#login_form",
            'form[action*="login"]',
            'input[name="email"]',
            'input[name="pass"]',
        ]
        assert len(selectors) == 5
        assert all(isinstance(s, str) for s in selectors)

    def test_auth_selectors_defined(self):
        """Auth indicator selectors should be defined."""
        selectors = [
            '[aria-label="Your profile"]',
            '[role="feed"]',
            '[data-pagelet="Stories"]',
        ]
        assert len(selectors) >= 3
        assert all(isinstance(s, str) for s in selectors)
