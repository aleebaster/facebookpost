"""
Browser management module.
Provides persistent Chrome profile using Playwright.
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


class BrowserManager:
    """Manages Chrome browser with persistent profile for Facebook sessions."""

    def __init__(
        self,
        user_data_dir: str = "",
        profile_name: str = "Profile 2",
        chrome_binary: str = "",
        headless: bool = False,
        slow_mo: int = 100,
    ):
        self.user_data_dir = user_data_dir
        self.profile_name = profile_name
        self.chrome_binary = chrome_binary
        self.headless = headless
        self.slow_mo = slow_mo

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(self) -> Page:
        """Launch Chrome with persistent profile and return a page."""
        logger.info("Starting Chrome Profile 2...")

        # Determine Chrome executable path
        chrome_path = self.chrome_binary or self._find_chrome_executable()
        if not chrome_path:
            logger.error("Chrome executable not found. Please set chrome_binary in config.yaml")
            raise RuntimeError("Chrome executable not found")

        # Determine user data directory
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        if not user_data:
            user_data = str(Path.cwd() / "profile")
            Path(user_data).mkdir(parents=True, exist_ok=True)
            logger.warning(f"No user_data_dir specified, using local: {user_data}")

        # Validate paths exist
        if not Path(chrome_path).exists():
            raise RuntimeError(f"Chrome executable not found at: {chrome_path}")
        if not Path(user_data).exists():
            raise RuntimeError(f"Chrome user data directory not found at: {user_data}")

        profile_path = Path(user_data) / self.profile_name
        if not profile_path.exists():
            logger.warning(f"Profile directory not found: {profile_path}")
            logger.warning("Chrome will create it, but it won't have your Facebook session")

        # HARD BLOCK: Check if Chrome is running
        # On Windows, Chrome locks the entire User Data directory.
        # Playwright cannot launch another Chrome with the same User Data dir.
        chrome_running = self._is_chrome_running()

        logger.info("Diagnostics:")
        logger.info(f"  Chrome process detected: {'YES' if chrome_running else 'NO'}")
        logger.info(f"  User data directory: {user_data}")
        logger.info(f"  Profile directory: {self.profile_name}")
        logger.info(f"  Chrome executable: {chrome_path}")

        if chrome_running:
            logger.error("")
            logger.error("=" * 60)
            logger.error("CHROME IS RUNNING - CANNOT LAUNCH BOT")
            logger.error("")
            logger.error("Playwright needs exclusive access to the Chrome")
            logger.error("User Data directory. Chrome is currently using it.")
            logger.error("")
            logger.error("TO FIX THIS:")
            logger.error("  1. Close ALL Chrome windows")
            logger.error("  2. Wait 3 seconds")
            logger.error("  3. Run the bot again")
            logger.error("")
            logger.error("After the bot finishes, you can reopen Chrome.")
            logger.error("")
            logger.error(f"  User data: {user_data}")
            logger.error(f"  Profile: {self.profile_name}")
            logger.error("=" * 60)
            raise RuntimeError(
                "Chrome is running. Close ALL Chrome windows and try again.\n"
                f"User data: {user_data}\n"
                f"Profile: {self.profile_name}"
            )

        self._playwright = await async_playwright().start()

        # Launch persistent context with the existing Chrome profile
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=user_data,
            executable_path=chrome_path,
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=[
                f"--profile-directory={self.profile_name}",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
            ],
            viewport={"width": 1280, "height": 900},
            locale="uk-UA",
            timezone_id="Europe/Kyiv",
        )

        # Diagnostic: show all pages in context
        page_count = len(self._context.pages)
        logger.info(f"Number of pages in context: {page_count}")
        for idx, pg in enumerate(self._context.pages):
            logger.info(f"  PAGE {idx}: {pg.url}")

        # Get or create a page
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

        logger.info("Browser started successfully")
        return self._page

    async def open_facebook(self) -> bool:
        """
        Navigate to Facebook homepage.
        This ensures the browser is NOT on about:blank.
        Returns True if navigation succeeded.
        """
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Opening Facebook:")
        logger.info("  https://www.facebook.com/")
        logger.info("Facebook navigation started...")

        try:
            before_url = self._page.url
            logger.info(f"Before navigation URL: {before_url}")

            await self._page.goto("https://www.facebook.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)

            current_url = self._page.url
            page_title = await self._page.title()

            logger.info(f"After navigation URL: {current_url}")
            logger.info(f"Page title: {page_title}")

            # CRITICAL CHECK: about:blank means navigation failed
            if current_url == "about:blank":
                logger.error("")
                logger.error("=" * 60)
                logger.error("CRITICAL NAVIGATION ERROR")
                logger.error("")
                logger.error("Expected:")
                logger.error("  https://www.facebook.com/")
                logger.error("")
                logger.error("Actual:")
                logger.error("  about:blank")
                logger.error("")
                logger.error("Facebook was NOT opened.")
                logger.error("Stopping workflow.")
                logger.error("=" * 60)
                await self._save_debug_screenshot("navigation_failure")
                return False

            if "facebook.com" in current_url:
                logger.info("Facebook loaded successfully.")
                logger.info(f"WORKING PAGE: {current_url}")
                return True
            else:
                logger.warning(f"Facebook did not load correctly. Current URL: {current_url}")
                await self._save_debug_screenshot("unexpected_url")
                return False
        except Exception as e:
            logger.error(f"Failed to open Facebook: {e}")
            await self._save_debug_screenshot("navigation_error")
            return False

    async def stop(self):
        """Close browser and clean up."""
        logger.info("Stopping browser...")
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        logger.info("Browser stopped")

    async def get_page(self) -> Page:
        """Get the current active page."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def new_page(self) -> Page:
        """Open a new page in the browser context."""
        if not self._context:
            raise RuntimeError("Browser not started. Call start() first.")
        self._page = await self._context.new_page()
        return self._page

    async def check_facebook_auth(self) -> bool:
        """Check if the user is logged into Facebook."""
        if not self._page:
            return False

        try:
            current_url = self._page.url
            if "facebook.com" not in current_url:
                logger.info("Not on Facebook yet, navigating...")
                nav_ok = await self.open_facebook()
                if not nav_ok:
                    return False

            logger.info("Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            logger.info(f"Current URL: {current_url}")

            # Check for login form
            login_form = await self._page.query_selector('button[data-testid="royal_login_button"]')
            if login_form:
                logger.warning("Facebook login form detected - user is NOT logged in")
                logger.info("Facebook session: NOT AUTHENTICATED")
                return False

            # Check for checkpoint
            checkpoint = await self._page.query_selector('[data-testid="checkpoint_title"]')
            if checkpoint:
                logger.warning("Facebook checkpoint detected - verification required")
                logger.info("Facebook session: NOT AUTHENTICATED (checkpoint)")
                return False

            # Check for profile icon or nav bar
            logged_in = await self._page.query_selector('[aria-label="Your profile"]') or \
                        await self._page.query_selector('[aria-label="\u041f\u0440\u043e\u0444\u0456\u043b\u044c"]') or \
                        await self._page.query_selector('svg[aria-label="Your profile"]')

            if logged_in:
                logger.info("Facebook session: AUTHENTICATED")
                return True

            # Additional check: post creation box
            post_box = await self._page.query_selector('[aria-label="Create a post"]') or \
                       await self._page.query_selector('[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]')
            if post_box:
                logger.info("Facebook session: AUTHENTICATED")
                return True

            # Check page URL
            if "facebook.com" in current_url and "/login" not in current_url and "/checkpoint" not in current_url:
                logged_in_indicators = [
                    '[aria-label="Home"]',
                    '[aria-label="\u0413\u043e\u043b\u043e\u0432\u043d\u0430"]',
                    '[data-pagelet="Stories"]',
                    '[role="feed"]',
                ]
                for indicator in logged_in_indicators:
                    element = await self._page.query_selector(indicator)
                    if element:
                        logger.info("Facebook session: AUTHENTICATED")
                        return True

            logger.warning("Could not confirm Facebook login status")
            logger.info("Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"Error checking Facebook auth: {e}")
            return False

    async def wait_for_login(self, timeout_minutes: int = 10):
        """Navigate to Facebook and wait for user to log in manually."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("Opening Facebook login page...")
        await self._page.goto("https://www.facebook.com/", wait_until="domcontentloaded")

        logger.info("=" * 60)
        logger.info("ACTION REQUIRED: Please log into Facebook in the browser window.")
        logger.info(f"Waiting up to {timeout_minutes} minutes...")
        logger.info("=" * 60)

        timeout_seconds = timeout_minutes * 60
        poll_interval = 5
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                logged_in = await self.check_facebook_auth()
                if logged_in:
                    logger.info("Login detected! Proceeding...")
                    return True
            except Exception:
                pass

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            if elapsed % 30 == 0:
                logger.info(f"Still waiting for login... ({elapsed // 60}m {elapsed % 60}s elapsed)")

        logger.error(f"Login timeout after {timeout_minutes} minutes")
        return False

    async def _save_debug_screenshot(self, name: str = "debug"):
        """Save a screenshot for debugging purposes."""
        try:
            if self._page:
                Path("logs").mkdir(parents=True, exist_ok=True)
                path = f"logs/{name}.png"
                await self._page.screenshot(path=path, full_page=False)
                logger.info(f"Debug screenshot saved: {path}")
        except Exception as e:
            logger.debug(f"Could not save debug screenshot: {e}")

    @staticmethod
    def _is_chrome_running() -> bool:
        """Check if any Chrome process is running on the system."""
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
                    capture_output=True, text=True, timeout=5
                )
                return "chrome.exe" in result.stdout.lower()
            else:
                result = subprocess.run(
                    ["pgrep", "-f", "chrome"],
                    capture_output=True, text=True, timeout=5
                )
                return result.returncode == 0
        except Exception:
            return False

    @staticmethod
    def _find_chrome_executable() -> str:
        """Find Chrome executable on the system."""
        import shutil

        possible_paths = []

        if sys.platform == "win32":
            possible_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Users\{}\AppData\Local\Google\Chrome\Application\chrome.exe".format(
                    Path.home().name
                ),
            ]
        elif sys.platform == "darwin":
            possible_paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            ]
        else:
            possible_paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ]

        for path in possible_paths:
            if Path(path).exists():
                return path

        for name in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
            found = shutil.which(name)
            if found:
                return found

        return ""

    @staticmethod
    def _get_default_user_data_dir() -> str:
        """Get default Chrome user data directory for the platform."""
        if sys.platform == "win32":
            return str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
        elif sys.platform == "darwin":
            return str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
        else:
            return str(Path.home() / ".config" / "google-chrome")
