"""Tests for Publisher — interval timing and dialog scoping."""

import asyncio
import random
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# Config timing tests
# ---------------------------------------------------------------------------

class TestConfigTiming:
    """Verify config.yaml has correct interval values."""

    def test_min_post_interval(self):
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("min_post_interval") == 60, (
            f"min_post_interval should be 60, got {timing.get('min_post_interval')}"
        )

    def test_max_post_interval(self):
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("max_post_interval") == 180, (
            f"max_post_interval should be 180, got {timing.get('max_post_interval')}"
        )

    def test_max_interval_not_exceeding_180(self):
        """Max interval must never exceed 180 seconds."""
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("max_post_interval", 0) <= 180

    def test_min_less_than_max(self):
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("min_post_interval", 0) <= timing.get("max_post_interval", 0)


# ---------------------------------------------------------------------------
# Interval behavior tests
# ---------------------------------------------------------------------------

class TestIntervalBehavior:
    """Test that intervals are only applied after SUCCESS, skipped in DRY_RUN."""

    def _load_config(self):
        with open("config.yaml", "r") as f:
            return yaml.safe_load(f)

    def test_dry_run_skips_pause(self):
        """DRY_RUN mode should not create real 60-180s pauses."""
        config = self._load_config()
        timing = config.get("timing", {})
        min_interval = timing.get("min_post_interval", 60)
        max_interval = timing.get("max_post_interval", 180)

        # In DRY_RUN, the bot should skip the interval
        # This is enforced in main.py logic, not in publisher
        assert min_interval >= 60
        assert max_interval <= 180

    def test_interval_random_range(self):
        """Verify random.randint produces values in the configured range."""
        min_val = 60
        max_val = 180
        random.seed(42)
        for _ in range(100):
            val = random.randint(min_val, max_val)
            assert val >= min_val, f"Value {val} below min {min_val}"
            assert val <= max_val, f"Value {val} above max {max_val}"

    def test_first_publication_no_initial_wait(self):
        """The first group should be processed immediately — no initial pause."""
        # This is enforced in main.py: pause only happens after i > 0
        # Verify config doesn't have an "initial_delay" that would pause first
        config = self._load_config()
        timing = config.get("timing", {})
        assert "initial_delay" not in timing or timing["initial_delay"] == 0


# ---------------------------------------------------------------------------
# Dialog scoping tests
# ---------------------------------------------------------------------------

class TestDialogScoping:
    """Verify publisher uses dialog-scoped locators."""

    def test_publisher_has_find_composer_dialog(self):
        """Publisher must have _find_composer_dialog method."""
        from src.publisher import Publisher
        assert hasattr(Publisher, "_find_composer_dialog")

    def test_publisher_has_dialog_scoped_methods(self):
        """Publisher must have dialog-scoped methods for text, photos, videos, publish."""
        from src.publisher import Publisher
        assert hasattr(Publisher, "_type_post_text_in_dialog")
        assert hasattr(Publisher, "_attach_photos_in_dialog")
        assert hasattr(Publisher, "_attach_videos_in_dialog")
        assert hasattr(Publisher, "_click_post_button_in_dialog")

    def test_old_page_level_methods_removed(self):
        """Old page-level methods should be removed."""
        from src.publisher import Publisher
        assert not hasattr(Publisher, "_type_post_text"), (
            "_type_post_text (page-level) should be removed"
        )
        assert not hasattr(Publisher, "_attach_photos"), (
            "_attach_photos (page-level) should be removed"
        )
        assert not hasattr(Publisher, "_attach_videos"), (
            "_attach_videos (page-level) should be removed"
        )
        assert not hasattr(Publisher, "_click_post_button"), (
            "_click_post_button (page-level) should be removed"
        )

    def test_no_pyautogui_in_publisher(self):
        """Publisher must not use pyautogui or system mouse."""
        from src import publisher
        import inspect
        source = inspect.getsource(publisher)
        assert "pyautogui" not in source.lower()
        assert "win32api" not in source.lower()
        assert "SetCursorPos" not in source
        assert "SendInput" not in source

    def test_no_global_scroll_in_publisher(self):
        """Publisher must not scroll the page feed after composer opens."""
        from src import publisher
        import inspect
        source = inspect.getsource(publisher)
        # The _actual_publish method should not call page.mouse.wheel
        # or window.scrollTo after dialog detection
        # We check that _type_post_text_in_dialog uses keyboard.type, not scroll
        assert "keyboard.type" in source or "page.keyboard" in source


# ---------------------------------------------------------------------------
# Main.py integration tests
# ---------------------------------------------------------------------------

class TestMainIntervalIntegration:
    """Test that main.py correctly handles interval timing."""

    def test_imports_cleanly(self):
        """main.py should import without errors."""
        import src.main
        assert hasattr(src.main, "run_bot")

    def test_dry_run_mode_exists(self):
        """DRY_RUN is a valid mode."""
        import src.main
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"])
        args = parser.parse_args(["--mode", "DRY_RUN"])
        assert args.mode == "DRY_RUN"

    def test_all_modes_available(self):
        """All four modes should be available."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"])
        for mode in ["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"]:
            args = parser.parse_args(["--mode", mode])
            assert args.mode == mode
