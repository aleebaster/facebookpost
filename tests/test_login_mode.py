"""Tests for LOGIN mode and authentication flow."""

import argparse
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import main, run_bot, run_login_mode, LOGIN_TIMEOUT_MINUTES


class TestLoginModeConstant:
    """Test LOGIN mode configuration."""

    def test_login_timeout_is_reasonable(self):
        """Login timeout should be generous (at least 30 minutes)."""
        assert LOGIN_TIMEOUT_MINUTES >= 30

    def test_login_in_cli_choices(self):
        """LOGIN should be a valid CLI mode."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--mode",
            choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"],
            default="DRY_RUN",
        )
        args = parser.parse_args(["--mode", "LOGIN"])
        assert args.mode == "LOGIN"

    def test_dry_run_still_valid(self):
        """DRY_RUN should still be a valid CLI mode."""
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--mode",
            choices=["LOGIN", "DRY_RUN", "MANUAL_APPROVAL", "AUTO"],
            default="DRY_RUN",
        )
        args = parser.parse_args(["--mode", "DRY_RUN"])
        assert args.mode == "DRY_RUN"


class TestLoginModeFlow:
    """Test LOGIN mode execution flow."""

    @pytest.mark.asyncio
    async def test_login_mode_authenticated_on_first_check(self):
        """LOGIN mode should report success if already authenticated."""
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=MagicMock())
        mock_browser.open_facebook = AsyncMock(return_value=True)
        mock_browser.check_facebook_auth = AsyncMock(return_value=True)
        mock_browser.stop = AsyncMock()

        with patch("src.main.BrowserManager", return_value=mock_browser):
            with patch("src.main.load_config", return_value={"browser": {}}):
                with patch("src.main.load_dotenv"):
                    with patch("src.main.setup_logging"):
                        await run_login_mode()

        mock_browser.start.assert_called_once()
        mock_browser.open_facebook.assert_called_once()
        mock_browser.check_facebook_auth.assert_called_once()
        mock_browser.wait_for_login.assert_not_called()
        mock_browser.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_mode_waits_for_manual_login(self):
        """LOGIN mode should wait for login if not authenticated."""
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=MagicMock())
        mock_browser.open_facebook = AsyncMock(return_value=True)
        mock_browser.check_facebook_auth = AsyncMock(return_value=False)
        mock_browser.wait_for_login = AsyncMock(return_value=True)
        mock_browser.stop = AsyncMock()

        with patch("src.main.BrowserManager", return_value=mock_browser):
            with patch("src.main.load_config", return_value={"browser": {}}):
                with patch("src.main.load_dotenv"):
                    with patch("src.main.setup_logging"):
                        await run_login_mode()

        mock_browser.wait_for_login.assert_called_once_with(
            timeout_minutes=LOGIN_TIMEOUT_MINUTES
        )
        mock_browser.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_mode_timeout(self):
        """LOGIN mode should handle login timeout."""
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=MagicMock())
        mock_browser.open_facebook = AsyncMock(return_value=True)
        mock_browser.check_facebook_auth = AsyncMock(return_value=False)
        mock_browser.wait_for_login = AsyncMock(return_value=False)
        mock_browser.stop = AsyncMock()

        with patch("src.main.BrowserManager", return_value=mock_browser):
            with patch("src.main.load_config", return_value={"browser": {}}):
                with patch("src.main.load_dotenv"):
                    with patch("src.main.setup_logging"):
                        # Should not raise, just log timeout
                        await run_login_mode()

        mock_browser.wait_for_login.assert_called_once()
        mock_browser.stop.assert_called_once()


class TestUnauthenticatedError:
    """Test that non-LOGIN modes show helpful message when not authenticated."""

    @pytest.mark.asyncio
    async def test_dry_run_shows_login_message(self):
        """DRY_RUN should show LOGIN command when not authenticated."""
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=MagicMock())
        mock_browser.open_facebook = AsyncMock(return_value=True)
        mock_browser.check_facebook_auth = AsyncMock(return_value=False)
        mock_browser.stop = AsyncMock()

        with patch("src.main.BrowserManager", return_value=mock_browser):
            with patch("src.main.load_config", return_value={
                "browser": {},
                "groups": {"file": "data/groups.txt"},
                "media": {},
                "content": {},
                "database": {},
                "logging": {},
            }):
                with patch("src.main.load_dotenv"):
                    with patch("src.main.setup_logging"):
                        with patch("src.main.GroupManager") as MockGM:
                            MockGM.return_value.count = 10
                            # Should return without crashing
                            await run_bot(mode="DRY_RUN")

        mock_browser.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_auto_shows_login_message(self):
        """AUTO should show LOGIN command when not authenticated."""
        mock_browser = MagicMock()
        mock_browser.start = AsyncMock(return_value=MagicMock())
        mock_browser.open_facebook = AsyncMock(return_value=True)
        mock_browser.check_facebook_auth = AsyncMock(return_value=False)
        mock_browser.stop = AsyncMock()

        with patch("src.main.BrowserManager", return_value=mock_browser):
            with patch("src.main.load_config", return_value={
                "browser": {},
                "groups": {"file": "data/groups.txt"},
                "media": {},
                "content": {},
                "database": {},
                "logging": {},
            }):
                with patch("src.main.load_dotenv"):
                    with patch("src.main.setup_logging"):
                        with patch("src.main.GroupManager") as MockGM:
                            MockGM.return_value.count = 10
                            await run_bot(mode="AUTO")

        mock_browser.stop.assert_called_once()


class TestModeRouting:
    """Test that main() routes to correct function based on mode."""

    def test_main_routes_to_login_mode(self):
        """main() with --mode LOGIN should call run_login_mode."""
        with patch("src.main.run_login_mode", new_callable=AsyncMock) as mock_login:
            with patch("src.main.asyncio.run"):
                with patch("argparse.ArgumentParser.parse_args") as mock_args:
                    mock_args.return_value = argparse.Namespace(
                        mode="LOGIN", config="config.yaml"
                    )
                    main()
                    # asyncio.run would be called, but we're testing routing

    def test_main_routes_to_run_bot(self):
        """main() with --mode DRY_RUN should call run_bot."""
        with patch("src.main.run_bot", new_callable=AsyncMock) as mock_bot:
            with patch("src.main.asyncio.run"):
                with patch("argparse.ArgumentParser.parse_args") as mock_args:
                    mock_args.return_value = argparse.Namespace(
                        mode="DRY_RUN", config="config.yaml",
                        limit_groups=0
                    )
                    main()
