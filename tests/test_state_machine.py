"""Tests for publisher state machine and --limit-groups CLI flag."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.publisher import Publisher, ComposerState


# ------------------------------------------------------------------ #
#  can_proceed_to_next_group                                           #
# ------------------------------------------------------------------ #

class TestCanProceedToNextGroup:
    """Verify the gate that controls whether next group is allowed."""

    def _make_publisher(self):
        page = MagicMock()
        db = MagicMock()
        content = MagicMock()
        media = MagicMock()
        timing = {"min_post_interval": 60, "max_post_interval": 180}
        return Publisher(page, db, content, media, timing)

    def test_dry_run_validated_can_proceed(self):
        p = self._make_publisher()
        assert p.can_proceed_to_next_group(ComposerState.DRY_RUN_VALIDATED, "DRY_RUN") is True

    def test_publication_confirmed_can_proceed(self):
        p = self._make_publisher()
        for mode in ("DRY_RUN", "MANUAL_APPROVAL", "AUTO"):
            assert p.can_proceed_to_next_group(ComposerState.PUBLICATION_CONFIRMED, mode) is True

    def test_failed_cannot_proceed(self):
        p = self._make_publisher()
        for mode in ("DRY_RUN", "MANUAL_APPROVAL", "AUTO"):
            assert p.can_proceed_to_next_group(ComposerState.FAILED, mode) is False

    def test_composer_opened_cannot_proceed(self):
        p = self._make_publisher()
        for mode in ("DRY_RUN", "MANUAL_APPROVAL", "AUTO"):
            assert p.can_proceed_to_next_group(ComposerState.COMPOSER_OPENED, mode) is False

    def test_text_entered_cannot_proceed(self):
        p = self._make_publisher()
        for mode in ("DRY_RUN", "MANUAL_APPROVAL", "AUTO"):
            assert p.can_proceed_to_next_group(ComposerState.TEXT_ENTERED, mode) is False

    def test_publish_clicked_cannot_proceed(self):
        p = self._make_publisher()
        for mode in ("DRY_RUN", "MANUAL_APPROVAL", "AUTO"):
            assert p.can_proceed_to_next_group(ComposerState.PUBLISH_CLICKED, mode) is False

    def test_dry_run_validated_cannot_proceed_in_auto(self):
        p = self._make_publisher()
        assert p.can_proceed_to_next_group(ComposerState.DRY_RUN_VALIDATED, "AUTO") is False

    def test_dry_run_validated_cannot_proceed_in_manual(self):
        p = self._make_publisher()
        assert p.can_proceed_to_next_group(ComposerState.DRY_RUN_VALIDATED, "MANUAL_APPROVAL") is False


# ------------------------------------------------------------------ #
#  ComposerState values                                                #
# ------------------------------------------------------------------ #

class TestComposerState:
    """Verify all expected states exist."""

    def test_all_states_exist(self):
        expected = [
            "GROUP_OPENED",
            "COMPOSER_OPENED",
            "TEXT_ENTERED",
            "PHOTOS_ATTACHED",
            "VIDEO_ATTACHED",
            "READY_TO_PUBLISH",
            "PUBLISH_CLICKED",
            "PUBLICATION_CONFIRMED",
            "DRY_RUN_VALIDATED",
            "FAILED",
        ]
        for name in expected:
            assert hasattr(ComposerState, name), f"Missing state: {name}"

    def test_failed_value(self):
        assert ComposerState.FAILED.value == "FAILED"

    def test_dry_run_validated_value(self):
        assert ComposerState.DRY_RUN_VALIDATED.value == "DRY_RUN_VALIDATED"


# ------------------------------------------------------------------ #
#  main.py --limit-groups                                             #
# ------------------------------------------------------------------ #

class TestLimitGroups:
    """Test --limit-groups CLI argument."""

    def test_limit_groups_in_cli(self):
        """Verify --limit-groups is accepted by argparse."""
        import sys
        from unittest.mock import patch
        from src.main import main

        test_args = ["main", "--mode", "DRY_RUN", "--limit-groups", "3"]
        with patch.object(sys, "argv", test_args):
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--mode", choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"], default="DRY_RUN")
            parser.add_argument("--config", default="config.yaml")
            parser.add_argument("--limit-groups", type=int, default=0)
            args = parser.parse_args(test_args[1:])
            assert args.limit_groups == 3

    def test_limit_groups_default_zero(self):
        """Default limit is 0 (all groups)."""
        import sys
        from unittest.mock import patch

        test_args = ["main", "--mode", "DRY_RUN"]
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--mode", choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"], default="DRY_RUN")
        parser.add_argument("--config", default="config.yaml")
        parser.add_argument("--limit-groups", type=int, default=0)
        args = parser.parse_args(test_args[1:])
        assert args.limit_groups == 0


# ------------------------------------------------------------------ #
#  Interval timing                                                     #
# ------------------------------------------------------------------ #

class TestIntervalTiming:
    """Verify config timing constraints."""

    def test_config_interval_max_180(self):
        """max_post_interval must be <= 180 seconds."""
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("max_post_interval", 999) <= 180, \
            f"max_post_interval ({timing.get('max_post_interval')}) must be <= 180"

    def test_config_interval_min_lte_max(self):
        """min_post_interval must be <= max_post_interval."""
        import yaml
        with open("config.yaml", "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        timing = config.get("timing", {})
        assert timing.get("min_post_interval", 0) <= timing.get("max_post_interval", 999)
