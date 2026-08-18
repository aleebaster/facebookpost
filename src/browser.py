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
          [1] Resolve paths (executable, user_data_dir, profile)
          [2] Validate paths exist
          [3] Check Chrome is NOT running (User Data would be locked)
          [4] Launch Chrome with --remote-debugging-port
          [5] Connect Playwright via CDP
          [6] Get working page from context
        """
        t0 = time.time()

        # ── [1] Resolve paths ──────────────────────────────────────────
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

        # ── [2] Validate paths ──────────────────────────────────────────
        logger.info("[1] Validating paths...")

        if not Path(chrome_path).exists():
            raise RuntimeError(
                f"Chrome executable not found: {chrome_path}\n"
                "Install Google Chrome or set browser.chrome_binary in config.yaml"
            )

        if not Path(user_data).exists():
            raise RuntimeError(f"User Data directory not found: {user_data}")

        if not profile_path.exists():
            raise RuntimeError(
                f"Profile not found: {profile_path}\n"
                f"Available profiles in {user_data}:"
            )

        logger.info("[1] All paths validated [OK]")

        # ── [3] Check Chrome is NOT running ─────────────────────────────
        logger.info("[2] Checking if Chrome is running...")
        chrome_running = self._is_chrome_running()
        logger.info(f"[2] Chrome running: {'YES' if chrome_running else 'NO'}")

        if chrome_running:
            raise RuntimeError(
                "Chrome is currently running and may lock the User Data directory.\n\n"
                "Please CLOSE ALL Chrome windows first, then run the bot again.\n\n"
                "Why: Chrome locks the entire User Data directory when running.\n"
                "The bot needs to launch its own Chrome instance with Profile 2.\n"
                "Both Chrome instances cannot share the same User Data directory.\n\n"
                "Steps:\n"
                "  1. Save any open work in Chrome\n"
                "  2. Close ALL Chrome windows\n"
                "  3. Wait 3 seconds\n"
                "  4. Run the bot again"
            )

        # ── [4] Launch Chrome with remote debugging ─────────────────────
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
            "--disable-blink-features=AutomationControlled",
        ]

        # Don't open about:blank — let Chrome open its default start page
        # We'll navigate to Facebook explicitly after connecting
        chrome_args.append("about:blank")

        try:
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to launch Chrome: {e}")

        logger.info(f"[3] Chrome started (PID: {self._chrome_process.pid})")

        # Wait for Chrome to fully start and open debugging port
        logger.info("[4] Waiting for Chrome debugging port...")
        port_ready = await self._wait_for_port(CDP_PORT, timeout=15)
        if not port_ready:
            raise RuntimeError(
                f"Chrome did not open debugging port {CDP_PORT} within 15 seconds.\n"
                "Chrome may have crashed. Check that the User Data directory is not locked."
            )
        logger.info(f"[4] Debugging port {CDP_PORT} ready [OK]")

        # ── [5] Connect Playwright via CDP ──────────────────────────────
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

        # ── [6] Get working page ────────────────────────────────────────
        logger.info("[6] Selecting working page...")
        contexts = self._browser.contexts

        if contexts:
            self._context = contexts[0]
            pages = self._context.pages
            logger.info(f"[6] Pages in context: {len(pages)}")
            for idx, pg in enumerate(pages):
                logger.info(f"    PAGE {idx}: {pg.url}")

            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()
        else:
            self._context = await self._browser.new_context()
            self._page = await self._context.new_page()

        logger.info(f"[6] Working page URL: {self._page.url}")

        total_time = time.time() - t0
        logger.info(f"[6] Browser started successfully ({total_time:.1f}s)")

        return self._page

    async def open_facebook(self) -> bool:
        """Navigate to Facebook homepage and verify it loads."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("[7] Opening Facebook:")
        logger.info("     https://www.facebook.com/")

        try:
            logger.info(f"[7] Current URL before: {self._page.url}")

            await self._page.goto(
                "https://www.facebook.com/",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await asyncio.sleep(3)

            current_url = self._page.url
            page_title = await self._page.title()

            logger.info(f"[7] After navigation: {current_url}")
            logger.info(f"[7] Page title: {page_title}")

            if current_url == "about:blank":
                logger.error("[7] CRITICAL NAVIGATION ERROR:")
                logger.error("     Expected: https://www.facebook.com/")
                logger.error("     Actual:   about:blank")
                logger.error("     Facebook was NOT opened.")
                logger.error("     Stopping workflow.")
                return False

            if "facebook.com" in current_url:
                logger.info("[7] Facebook loaded successfully.")
                logger.info(f"     WORKING PAGE: {current_url}")
                return True
            else:
                logger.warning(f"[7] Unexpected URL after Facebook navigation: {current_url}")
                return False

        except Exception as e:
            logger.error(f"[7] Failed to open Facebook: {e}")
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
                logger.info("[8] Not on Facebook, navigating...")
                nav_ok = await self.open_facebook()
                if not nav_ok:
                    return False

            logger.info("[8] Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            logger.info(f"[8] Current URL: {current_url}")

            # Check for login form indicators
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
                        logger.warning("[8] Login form detected - NOT authenticated")
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
                        logger.warning("[8] Checkpoint detected")
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
                        logger.info("[8] Facebook session: AUTHENTICATED")
                        return True
                except Exception:
                    continue

            # URL-based fallback: on facebook.com, not login/checkpoint
            if (
                "facebook.com" in current_url
                and "/login" not in current_url
                and "/checkpoint" not in current_url
            ):
                # If we're on a facebook.com page that isn't login, probably authenticated
                logger.info("[8] Facebook session: AUTHENTICATED (URL-based check)")
                return True

            logger.warning("[8] Could not confirm login status")
            logger.info("[8] Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"[8] Error checking auth: {e}")
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

    # ── Private helpers ─────────────────────────────────────────────────

    @staticmethod
    def _is_chrome_running() -> bool:
        """Check if any Chrome process is running."""
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                # Parse output lines — only count actual process lines
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    if "chrome.exe" in line.lower():
                        # Verify it's a real process line by checking for PID (digits)
                        parts = line.split()
                        if parts and parts[0].lower() == "chrome.exe":
                            return True
                return False
            else:
                result = subprocess.run(
                    ["pgrep", "-f", "chrome"],
                    capture_output=True,
                    timeout=5,
                )
                return result.returncode == 0
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
