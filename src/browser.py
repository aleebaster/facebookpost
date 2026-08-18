"""
Browser management module.
Provides persistent Chrome profile using Playwright.

Root cause of previous hang: Chrome's User Data directory is too large
(multiple profiles, cache, extensions). Playwright's launch_persistent_context
hangs when processing it directly. Fix: copy Profile 2 to a clean temp
directory and use that as user_data_dir. This preserves Facebook cookies.
"""

import asyncio
import shutil
import subprocess
import sys
import tempfile
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
        self._temp_dir: Optional[str] = None

    async def start(self) -> Page:
        """Launch Chrome with persistent profile and return a page."""
        t0 = time.time()
        logger.info("[1] Starting Chrome Profile 2...")

        # [2] Check Chrome executable
        chrome_path = self.chrome_binary or self._find_chrome_executable()
        if not chrome_path or not Path(chrome_path).exists():
            logger.error(f"[2] Chrome executable NOT FOUND")
            raise RuntimeError("Chrome executable not found")
        logger.info(f"[2] Chrome executable: {chrome_path}")

        # [3] Check User Data directory
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        if not user_data or not Path(user_data).exists():
            logger.error(f"[3] User data directory NOT FOUND: {user_data}")
            raise RuntimeError(f"Chrome user data directory not found")
        logger.info(f"[3] User data directory: {user_data}")

        # [4] Check Profile 2
        source_profile = Path(user_data) / self.profile_name
        logger.info(f"[4] Profile 2 source: {source_profile}")
        logger.info(f"[4] Profile 2 exists: {'YES' if source_profile.exists() else 'NO'}")
        if not source_profile.exists():
            logger.error("[4] Profile 2 does not exist - cannot use existing session")
            raise RuntimeError(f"Profile 2 not found at {source_profile}")

        # [5] Copy Profile 2 to temp directory
        # This avoids the hang caused by the large User Data directory
        self._temp_dir = tempfile.mkdtemp(prefix="fb_bot_")
        temp_user_data = str(Path(self._temp_dir) / "User Data")
        temp_profile = Path(temp_user_data) / self.profile_name

        logger.info("[5] Copying Profile 2 to temp directory...")
        logger.info(f"    Source: {source_profile}")
        logger.info(f"    Target: {temp_profile}")

        try:
            self._copy_profile(source_profile, temp_profile)
            file_count = len(list(temp_profile.rglob("*")))
            logger.info(f"[5] Profile copied: {file_count} files")
        except Exception as e:
            logger.error(f"[5] Failed to copy profile: {e}")
            self._cleanup_temp()
            raise

        # [6] Start Playwright
        logger.info("[6] Starting Playwright...")
        self._playwright = await async_playwright().start()
        logger.info("[6] Playwright started")

        # [7] Launch persistent context with copied profile
        logger.info("[7] Launching persistent Chrome context...")
        launch_start = time.time()
        try:
            self._context = await asyncio.wait_for(
                self._playwright.chromium.launch_persistent_context(
                    user_data_dir=temp_user_data,
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
                timeout=30,
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - launch_start
            logger.error(f"[7] TIMEOUT after {elapsed:.1f}s")
            self._cleanup_temp()
            raise RuntimeError(
                f"Chrome launch timed out after {elapsed:.1f}s. "
                "Close ALL Chrome windows and try again."
            )
        except Exception as e:
            elapsed = time.time() - launch_start
            logger.error(f"[7] FAILED after {elapsed:.1f}s: {e}")
            self._cleanup_temp()
            raise

        elapsed = time.time() - launch_start
        logger.info(f"[7] Context created in {elapsed:.1f}s")

        # [8] Check pages in context
        page_count = len(self._context.pages)
        logger.info(f"[8] Pages in context: {page_count}")
        for idx, pg in enumerate(self._context.pages):
            logger.info(f"    PAGE {idx}: {pg.url}")

        # [9] Select working page
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        logger.info(f"[9] Working page URL: {self._page.url}")

        total_time = time.time() - t0
        logger.info(f"[10] Browser started successfully ({total_time:.1f}s)")
        return self._page

    async def open_facebook(self) -> bool:
        """Navigate to Facebook homepage."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("[11] Opening Facebook...")
        logger.info("     https://www.facebook.com/")

        try:
            before_url = self._page.url
            logger.info(f"[11] Before navigation: {before_url}")

            await self._page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(3)

            current_url = self._page.url
            page_title = await self._page.title()

            logger.info(f"[11] After navigation: {current_url}")
            logger.info(f"[11] Page title: {page_title}")

            if current_url == "about:blank":
                logger.error("[11] CRITICAL: Facebook did NOT load. Browser is on about:blank")
                await self._save_debug_screenshot("navigation_failure")
                return False

            if "facebook.com" in current_url:
                logger.info(f"[11] Facebook loaded successfully. WORKING PAGE: {current_url}")
                return True
            else:
                logger.warning(f"[11] Unexpected URL: {current_url}")
                await self._save_debug_screenshot("unexpected_url")
                return False
        except Exception as e:
            logger.error(f"[11] Failed to open Facebook: {e}")
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
        self._cleanup_temp()
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
                logger.info("[12] Not on Facebook, navigating...")
                nav_ok = await self.open_facebook()
                if not nav_ok:
                    return False

            logger.info("[12] Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            logger.info(f"[12] Current URL: {current_url}")

            # Check for login form
            login_form = await self._page.query_selector('button[data-testid="royal_login_button"]')
            if login_form:
                logger.warning("[12] Login form detected - NOT authenticated")
                return False

            # Check for checkpoint
            checkpoint = await self._page.query_selector('[data-testid="checkpoint_title"]')
            if checkpoint:
                logger.warning("[12] Checkpoint detected")
                return False

            # Check for profile icon
            logged_in = await self._page.query_selector('[aria-label="Your profile"]') or \
                        await self._page.query_selector('[aria-label="\u041f\u0440\u043e\u0444\u0456\u043b\u044c"]') or \
                        await self._page.query_selector('svg[aria-label="Your profile"]')

            if logged_in:
                logger.info("[12] Facebook session: AUTHENTICATED")
                return True

            # Check for post creation box
            post_box = await self._page.query_selector('[aria-label="Create a post"]') or \
                       await self._page.query_selector('[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]')
            if post_box:
                logger.info("[12] Facebook session: AUTHENTICATED")
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
                        logger.info("[12] Facebook session: AUTHENTICATED")
                        return True

            logger.warning("[12] Could not confirm login status")
            logger.info("[12] Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"[12] Error checking auth: {e}")
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

    def _copy_profile(self, source: Path, target: Path):
        """Copy Chrome profile directory, skipping large/unnecessary files."""
        target.mkdir(parents=True, exist_ok=True)

        # Files/folders to skip (large, not needed)
        skip_dirs = {"Cache", "Code Cache", "GPUCache", "Service Worker",
                     "IndexedDB", "Local Storage", "Session Storage",
                     "WebStorage", "blob_storage", "databases",
                     "File System", "GCM Store", "Platform Notifications",
                     "Sync Extension Settings", "BudgetDatabase",
                     "heavy_ad_intervention", "safe_browsing"}

        for item in source.iterdir():
            # Skip directories we don't need
            if item.is_dir() and item.name in skip_dirs:
                continue

            # Skip large files
            if item.is_file() and item.stat().st_size > 10 * 1024 * 1024:  # > 10MB
                continue

            dst = target / item.name
            try:
                if item.is_dir():
                    shutil.copytree(item, dst, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns(*skip_dirs))
                else:
                    shutil.copy2(item, dst)
            except (PermissionError, OSError):
                pass

        # Always copy Network/Cookies (essential for session)
        network_src = source / "Network"
        if network_src.exists():
            network_dst = target / "Network"
            try:
                shutil.copytree(network_src, network_dst, dirs_exist_ok=True)
            except (PermissionError, OSError):
                pass

        # Also copy Local State from User Data root (contains cookie encryption key)
        local_state = source.parent.parent / "Local State"
        if local_state.exists():
            local_state_dst = target.parent.parent / "Local State"
            try:
                shutil.copy2(local_state, local_state_dst)
            except (PermissionError, OSError):
                pass

    def _cleanup_temp(self):
        """Clean up temporary profile directory."""
        if self._temp_dir and Path(self._temp_dir).exists():
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass
            self._temp_dir = None

    @staticmethod
    def _find_chrome_executable() -> str:
        """Find Chrome executable on the system."""
        import shutil as _shutil

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
            found = _shutil.which(name)
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
