"""
Browser management module.

Launches system Google Chrome with --remote-debugging-port and the user's
existing Chrome Profile 2, then connects via Chrome DevTools Protocol (CDP).

Architecture:
  Python -> Playwright CDP client -> System Google Chrome -> User Data/Profile 2 -> Facebook session

IMPORTANT: Chrome must be CLOSED before running the bot.
The bot launches its own Chrome instance with the user's profile.
"""

import asyncio
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright


# Chrome debugging port
CDP_PORT = 9222


class BrowserManager:
    """Manages system Chrome via Chrome DevTools Protocol (CDP)."""

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
        self._chrome_process: Optional[subprocess.Popen] = None

    async def start(self) -> Page:
        """
        Launch system Chrome with Profile 2 and connect via CDP.

        Steps:
          [1] Resolve and validate paths
          [2] Check Chrome is NOT running
          [3] Launch Chrome with --remote-debugging-port
          [4] Connect Playwright via CDP
          [5] Close all default about:blank pages
          [6] Create ONE working page
          [7] Navigate to Facebook
          [8] Verify Facebook loaded
        """
        t0 = time.time()

        # -- [1] Resolve paths --
        chrome_path = self.chrome_binary or self._find_chrome_executable()
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        profile_path = Path(user_data) / self.profile_name

        logger.info("=" * 60)
        logger.info("BROWSER CONFIGURATION")
        logger.info("=" * 60)
        logger.info("Browser: SYSTEM GOOGLE CHROME")
        logger.info(f"  Executable:     {chrome_path}")
        logger.info(f"  User Data:      {user_data}")
        logger.info(f"  Profile:        {self.profile_name}")
        logger.info(f"  Profile path:   {profile_path}")
        logger.info(f"  CDP port:       {CDP_PORT}")
        logger.info("=" * 60)

        # -- [2] Validate paths --
        logger.info("[1] Validating paths...")
        if not Path(chrome_path).exists():
            raise RuntimeError(
                f"Chrome executable not found: {chrome_path}\n"
                "Install Google Chrome or set browser.chrome_binary in config.yaml"
            )
        if not Path(user_data).exists():
            raise RuntimeError(f"User Data directory not found: {user_data}")
        if not profile_path.exists():
            raise RuntimeError(f"Profile not found: {profile_path}")
        logger.info("[1] All paths validated [OK]")

        # -- [3] Check if CDP port is available --
        logger.info("[2] Checking CDP port 9222...")
        port_busy = await self._is_port_in_use(CDP_PORT)
        logger.info(f"[2] Port {CDP_PORT}: {'IN USE' if port_busy else 'FREE'}")

        if port_busy:
            raise RuntimeError(
                f"CDP port {CDP_PORT} is already in use.\n\n"
                "Another Chrome instance may be using this port.\n"
                "Close other Chrome windows and try again."
            )

        # -- [4] Launch Chrome with remote debugging --
        # NO initial URL — Chrome opens its default new tab.
        # We will close all tabs and create a fresh one for Facebook.
        logger.info("[3] Launching system Chrome...")
        logger.info(f"    chrome.exe --remote-debugging-port={CDP_PORT}")
        logger.info(f"    --user-data-dir={user_data}")
        logger.info(f"    --profile-directory={self.profile_name}")

        chrome_args = [
            chrome_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={user_data}",
            f"--profile-directory={self.profile_name}",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        try:
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to launch Chrome: {e}")

        logger.info(f"[3] Chrome started (PID: {self._chrome_process.pid})")

        # Wait for debugging port
        logger.info("[4] Waiting for Chrome debugging port...")
        port_ready = await self._wait_for_port(CDP_PORT, timeout=15)
        if not port_ready:
            raise RuntimeError(
                f"Chrome did not open debugging port {CDP_PORT} within 15 seconds.\n"
                "Chrome may have crashed. Check that the User Data directory is not locked."
            )
        logger.info(f"[4] Debugging port {CDP_PORT} ready [OK]")

        # -- [5] Connect Playwright via CDP --
        logger.info("[5] Connecting Playwright to Chrome via CDP...")
        self._playwright = await async_playwright().start()

        try:
            self._browser = await asyncio.wait_for(
                self._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{CDP_PORT}"
                ),
                timeout=10,
            )
        except asyncio.TimeoutError:
            raise RuntimeError("Timeout connecting to Chrome via CDP")

        logger.info("[5] Connected to Chrome via CDP [OK]")

        # -- [6] List ALL contexts and pages --
        logger.info("[6] Listing all contexts and pages...")
        for ctx_idx, ctx in enumerate(self._browser.contexts):
            logger.info(f"    Context {ctx_idx}: {len(ctx.pages)} page(s)")
            for pg_idx, pg in enumerate(ctx.pages):
                logger.info(f"      Page {pg_idx}: {pg.url}")

        # Get the default context (first one)
        if not self._browser.contexts:
            self._context = await self._browser.new_context()
        else:
            self._context = self._browser.contexts[0]

        logger.info(f"[6] Using context with {len(self._context.pages)} page(s)")

        # -- [7] Close ALL existing pages (they are about:blank from Chrome startup) --
        logger.info("[7] Closing default pages...")
        existing_pages = list(self._context.pages)
        for pg in existing_pages:
            try:
                await pg.close()
                logger.info(f"    Closed: {pg.url}")
            except Exception as e:
                logger.debug(f"    Could not close page: {e}")

        # -- [8] Create ONE fresh working page --
        logger.info("[8] Creating fresh working page...")
        self._page = await self._context.new_page()

        working_url = self._page.url
        logger.info(f"[8] Working page created: {working_url}")

        total_time = time.time() - t0
        logger.info(f"[8] Browser connected ({total_time:.1f}s)")

        return self._page

    async def open_facebook(self) -> bool:
        """
        Navigate to Facebook homepage and verify it loads.
        """
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("[9] Opening Facebook:")
        logger.info("     https://www.facebook.com/")
        logger.info(f"[9] URL before navigation: {self._page.url}")

        try:
            # Navigate to Facebook
            await self._page.goto(
                "https://www.facebook.com/",
                wait_until="load",
                timeout=60000,
            )

            # Wait for network to settle
            try:
                await self._page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                logger.info("[9] networkidle timeout — proceeding")

            # Extra wait for dynamic content
            await asyncio.sleep(5)

            # -- Verify with multiple methods --
            page_url = self._page.url
            doc_url = await self._page.evaluate("window.location.href")
            page_title = await self._page.title()

            logger.info("[9] Navigation verification:")
            logger.info(f"     page.url:          {page_url}")
            logger.info(f"     document.location: {doc_url}")
            logger.info(f"     page title:        {page_title}")

            # List ALL pages after navigation
            logger.info("[9] All pages after navigation:")
            for idx, pg in enumerate(self._context.pages):
                logger.info(f"     [{idx}] {pg.url}")

            # Take screenshot
            screenshot_path = "logs/facebook_after_navigation.png"
            try:
                Path("logs").mkdir(exist_ok=True)
                await self._page.screenshot(path=screenshot_path)
                logger.info(f"[9] Screenshot: {screenshot_path}")
            except Exception as e:
                logger.warning(f"[9] Screenshot failed: {e}")

            # -- Critical checks --
            if page_url == "about:blank" and doc_url == "about:blank":
                logger.error("[9] CRITICAL NAVIGATION ERROR:")
                logger.error("     Expected: https://www.facebook.com/")
                logger.error(f"     page.url: {page_url}")
                logger.error(f"     document.location.href: {doc_url}")
                logger.error("     Facebook was NOT opened. Stopping workflow.")
                return False

            if "facebook.com" in page_url or "facebook.com" in doc_url:
                logger.info("[9] Facebook loaded successfully.")
                logger.info(f"     WORKING PAGE: {page_url}")
                return True
            else:
                logger.warning(f"[9] Unexpected URL: {page_url}")
                return False

        except Exception as e:
            logger.error(f"[9] Failed to open Facebook: {e}")
            return False

    async def stop(self):
        """Disconnect from Chrome and clean up."""
        logger.info("Disconnecting from Chrome...")
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
        self._page = None
        logger.info("Disconnected")

    async def get_page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started.")
        return self._page

    async def check_facebook_auth(self) -> bool:
        """Check if the user is logged into Facebook."""
        if not self._page:
            return False

        try:
            current_url = self._page.url
            if "facebook.com" not in current_url:
                logger.info("[10] Not on Facebook, navigating...")
                nav_ok = await self.open_facebook()
                if not nav_ok:
                    return False

            logger.info("[10] Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            doc_url = await self._page.evaluate("window.location.href")
            logger.info(f"[10] page.url: {current_url}")
            logger.info(f"[10] document.location.href: {doc_url}")

            # Check for login form
            login_selectors = [
                'button[data-testid="royal_login_button"]',
                '#login_form',
                'form[action*="login"]',
                'input[name="email"]',
                'input[name="pass"]',
            ]
            for sel in login_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        logger.warning("[10] Login form detected - NOT authenticated")
                        return False
                except Exception:
                    continue

            # Check for checkpoint
            checkpoint_selectors = [
                '[data-testid="checkpoint_title"]',
                'div[class*="checkpoint"]',
            ]
            for sel in checkpoint_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        logger.warning("[10] Checkpoint detected")
                        return False
                except Exception:
                    continue

            # Check for authenticated indicators
            auth_selectors = [
                '[aria-label="Your profile"]',
                '[aria-label="\u041f\u0440\u043e\u0444\u0456\u043b\u044c"]',
                'svg[aria-label="Your profile"]',
                '[aria-label="Home"]',
                '[aria-label="\u0413\u043e\u043b\u043e\u0432\u043d\u0430"]',
                '[role="feed"]',
                '[data-pagelet="Stories"]',
                '[aria-label="Create a post"]',
                '[aria-label="\u0421\u0442\u0432\u043e\u0440\u0438\u0442\u0438 \u0434\u043e\u043f\u0438\u0441"]',
            ]
            for sel in auth_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        logger.info("[10] Facebook session: AUTHENTICATED")
                        return True
                except Exception:
                    continue

            # URL-based fallback
            url_to_check = doc_url if doc_url else current_url
            if (
                "facebook.com" in url_to_check
                and "/login" not in url_to_check
                and "/checkpoint" not in url_to_check
            ):
                logger.info("[10] Facebook session: AUTHENTICATED (URL-based)")
                return True

            logger.warning("[10] Could not confirm login status")
            logger.info("[10] Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"[10] Error checking auth: {e}")
            return False

    async def wait_for_login(self, timeout_minutes: int = 10):
        """Wait for user to log in manually in the Chrome window."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        logger.info("=" * 60)
        logger.info("Waiting for Facebook login...")
        logger.info("Please log into Facebook in the Chrome window.")
        logger.info(f"Waiting up to {timeout_minutes} minutes...")
        logger.info("=" * 60)

        timeout_seconds = timeout_minutes * 60
        poll_interval = 5
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                logged_in = await self.check_facebook_auth()
                if logged_in:
                    logger.info("Login detected!")
                    return True
            except Exception:
                pass

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

            if elapsed % 30 == 0:
                logger.info(f"Waiting... ({elapsed // 60}m {elapsed % 60}s)")

        logger.error(f"Login timeout after {timeout_minutes} minutes")
        return False

    # -- Private helpers --

    @staticmethod
    async def _is_port_in_use(port: int) -> bool:
        """Check if a TCP port is already in use."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port),
                timeout=2,
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
            return False
        except Exception:
            return False

    @staticmethod
    async def _wait_for_port(port: int, timeout: int = 15) -> bool:
        """Wait for a TCP port to become available."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", port),
                    timeout=2,
                )
                writer.close()
                await writer.wait_closed()
                return True
            except (ConnectionRefusedError, OSError, asyncio.TimeoutError):
                await asyncio.sleep(0.5)
            except Exception:
                await asyncio.sleep(0.5)
        return False

    @staticmethod
    def _find_chrome_executable() -> str:
        """Find Chrome executable on the system."""
        import shutil

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
