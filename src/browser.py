"""
Browser management module.
Provides persistent Chrome profile using Playwright.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

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
        t0 = time.time()
        logger.info("[1] Starting Chrome Profile 2...")

        # [2] Check Chrome process
        chrome_running = self._is_chrome_running()
        logger.info(f"[2] Chrome process: {'RUNNING' if chrome_running else 'NOT RUNNING'}")

        if chrome_running:
            self._log_chrome_block()
            raise RuntimeError("Chrome is running. Close ALL Chrome windows and try again.")

        # [3] Check Chrome executable
        chrome_path = self.chrome_binary or self._find_chrome_executable()
        if not chrome_path or not Path(chrome_path).exists():
            logger.error(f"[3] Chrome executable NOT FOUND")
            raise RuntimeError("Chrome executable not found")
        logger.info(f"[3] Chrome executable: {chrome_path}")

        # [4] Check User Data directory
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        if not user_data or not Path(user_data).exists():
            logger.error(f"[4] User data directory NOT FOUND: {user_data}")
            raise RuntimeError(f"Chrome user data directory not found")
        logger.info(f"[4] User data directory: {user_data}")

        # [5] Check Profile 2
        profile_path = Path(user_data) / self.profile_name
        logger.info(f"[5] Profile 2 exists: {'YES' if profile_path.exists() else 'NO'}")
        if not profile_path.exists():
            logger.warning("[5] Profile directory not found - Chrome will create it")

        # [6] Check lock files at BOTH levels
        user_data_locked = self._is_user_data_locked(user_data)
        profile_locked = self._is_profile_locked(user_data, self.profile_name)
        logger.info(f"[6] User Data locked: {'YES' if user_data_locked else 'NO'}")
        logger.info(f"[6] Profile 2 locked: {'YES' if profile_locked else 'NO'}")

        if user_data_locked or profile_locked:
            self._log_chrome_block()
            raise RuntimeError(
                "Chrome User Data or Profile 2 is locked. "
                "Close ALL Chrome windows, wait 5 seconds, and try again."
            )

        # [7] Start Playwright
        logger.info("[7] Starting Playwright...")
        self._playwright = await async_playwright().start()
        logger.info("[7] Playwright started")

        # [8] Launch persistent context
        logger.info("[8] Launching persistent Chrome context...")
        launch_start = time.time()
        try:
            self._context = await asyncio.wait_for(
                self._playwright.chromium.launch_persistent_context(
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
                ),
                timeout=20,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - launch_start
            logger.error(f"[8] TIMEOUT after {elapsed:.1f}s")
            logger.error("Chrome persistent context launch timed out.")
            logger.error("")
            logger.error("This usually means:")
            logger.error("  - Chrome User Data is still locked")
            logger.error("  - Chrome process is residual (kill chrome.exe)")
            logger.error("  - Profile directory is corrupted")
            logger.error("")
            logger.error("Try: close Chrome, wait 5 seconds, run again.")
            logger.error("If still fails, restart your computer.")
            raise RuntimeError(
                f"Chrome launch timed out after {elapsed:.1f}s. "
                "Close ALL Chrome windows and try again."
            )
        except Exception as e:
            elapsed = time.time() - launch_start
            logger.error(f"[8] FAILED after {elapsed:.1f}s: {e}")
            raise

        elapsed = time.time() - launch_start
        logger.info(f"[8] Context created in {elapsed:.1f}s")

        # [9] Check pages in context
        page_count = len(self._context.pages)
        logger.info(f"[9] Pages in context: {page_count}")
        for idx, pg in enumerate(self._context.pages):
            logger.info(f"    PAGE {idx}: {pg.url}")

        # [10] Select working page
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        logger.info(f"[10] Working page URL: {self._page.url}")

        total_time = time.time() - t0
        logger.info(f"[11] Browser started successfully ({total_time:.1f}s)")
        return self._page

    async def open_facebook(self) -> bool:
        """Navigate to Facebook homepage."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("[12] Opening Facebook...")
        logger.info("     https://www.facebook.com/")

        try:
            before_url = self._page.url
            logger.info(f"[12] Before navigation: {before_url}")

            await self._page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(3)

            current_url = self._page.url
            page_title = await self._page.title()

            logger.info(f"[12] After navigation: {current_url}")
            logger.info(f"[12] Page title: {page_title}")

            if current_url == "about:blank":
                logger.error("[12] CRITICAL: Facebook did NOT load. Browser is on about:blank")
                await self._save_debug_screenshot("navigation_failure")
                return False

            if "facebook.com" in current_url:
                logger.info(f"[12] Facebook loaded successfully. WORKING PAGE: {current_url}")
                return True
            else:
                logger.warning(f"[12] Unexpected URL: {current_url}")
                await self._save_debug_screenshot("unexpected_url")
                return False
        except Exception as e:
            logger.error(f"[12] Failed to open Facebook: {e}")
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
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def new_page(self) -> Page:
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
                logger.info("[13] Not on Facebook, navigating...")
                nav_ok = await self.open_facebook()
                if not nav_ok:
                    return False

            logger.info("[13] Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            logger.info(f"[13] Current URL: {current_url}")

            # Check for login form
            login_form = await self._page.query_selector('button[data-testid="royal_login_button"]')
            if login_form:
                logger.warning("[13] Login form detected - NOT authenticated")
                return False

            # Check for checkpoint
            checkpoint = await self._page.query_selector('[data-testid="checkpoint_title"]')
            if checkpoint:
                logger.warning("[13] Checkpoint detected")
                return False

            # Check for profile icon
            logged_in = await self._page.query_selector('[aria-label="Your profile"]') or \
                        await self._page.query_selector('[aria-label="\u041f\u0440\u043e\u0444\u0456\u043b\u044c"]') or \
                        await self._page.query_selector('svg[aria-label="Your profile"]')

            if logged_in:
                logger.info("[13] Facebook session: AUTHENTICATED")
                return True

            # Check for post creation box
            post_box = await self._page.query_selector('[aria-label="Create a post"]') or \
                       await self._page.query_selector('[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]')
            if post_box:
                logger.info("[13] Facebook session: AUTHENTICATED")
                return True

            # Check page URL indicators
            if "facebook.com" in current_url and "/login" not in current_url and "/checkpoint" not in current_url:
                indicators = [
                    '[aria-label="Home"]',
                    '[aria-label="\u0413\u043e\u043b\u043e\u0432\u043d\u0430"]',
                    '[data-pagelet="Stories"]',
                    '[role="feed"]',
                ]
                for indicator in indicators:
                    element = await self._page.query_selector(indicator)
                    if element:
                        logger.info("[13] Facebook session: AUTHENTICATED")
                        return True

            logger.warning("[13] Could not confirm login status")
            logger.info("[13] Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"[13] Error checking auth: {e}")
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
        except Exception:
            pass

    def _log_chrome_block(self):
        """Log the Chrome block message."""
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        logger.error("")
        logger.error("=" * 60)
        logger.error("CHROME IS RUNNING OR USER DATA IS LOCKED")
        logger.error("")
        logger.error("Playwright needs exclusive access to the Chrome")
        logger.error("User Data directory. It is currently locked.")
        logger.error("")
        logger.error("TO FIX:")
        logger.error("  1. Close ALL Chrome windows")
        logger.error("  2. Wait 5 seconds")
        logger.error("  3. Run the bot again")
        logger.error("")
        logger.error(f"  User data: {user_data}")
        logger.error(f"  Profile: {self.profile_name}")
        logger.error("=" * 60)

    @staticmethod
    def _is_user_data_locked(user_data_dir: str) -> bool:
        """Check if Chrome User Data directory has active locks."""
        # Check for SingletonLock (strong indicator of active Chrome)
        singleton = Path(user_data_dir) / "SingletonLock"
        if singleton.exists():
            return True

        # Check for non-empty lockfile
        lockfile = Path(user_data_dir) / "lockfile"
        if lockfile.exists() and lockfile.stat().st_size > 0:
            return True

        return False

    @staticmethod
    def _is_profile_locked(user_data_dir: str, profile_name: str = "Profile 2") -> bool:
        """Check if a specific Chrome profile is locked."""
        profile_path = Path(user_data_dir) / profile_name
        if not profile_path.exists():
            return False

        for name in ["SingletonLock", "lockfile"]:
            lock_path = profile_path / name
            if lock_path.exists():
                return True

        return False

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
