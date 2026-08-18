"""
Browser management module.

Uses a DEDICATED Chrome User Data directory for the bot:
  bot_chrome_data/

The bot NEVER touches the user's original Chrome User Data.
The bot NEVER creates junctions or copies profiles.
The bot NEVER kills other Chrome processes.

Architecture:
  Python -> Playwright CDP client -> System Google Chrome -> bot_chrome_data

Session persistence:
  After LOGIN, Facebook session is stored in bot_chrome_data.
  Subsequent runs use the same directory automatically.
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

# Dedicated bot Chrome User Data directory
BOT_USER_DATA_DIR = "bot_chrome_data"


class BrowserManager:
    """Manages a dedicated system Chrome instance via Chrome DevTools Protocol (CDP).

    The bot uses its OWN Chrome User Data directory (bot_chrome_data/),
    completely separate from the user's regular Chrome.
    """

    def __init__(
        self,
        user_data_dir: str = "",
        profile_name: str = "Default",
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
        self._bot_chrome_pid: Optional[int] = None

    @property
    def bot_chrome_pid(self) -> Optional[int]:
        """Return the PID of the bot's own Chrome instance."""
        return self._bot_chrome_pid

    async def start(self) -> Page:
        """
        Launch system Chrome with dedicated bot User Data via CDP.

        Steps:
          [1] Resolve and validate paths
          [2] Ensure bot Chrome User Data exists
          [3] Launch Chrome with bot_chrome_data + CDP
          [4] Wait for CDP port
          [5] Connect Playwright via CDP
          [6] Select working page
        """
        t0 = time.time()

        # -- [1] Resolve and validate paths --
        chrome_path = self.chrome_binary or self._find_chrome_executable()

        # Determine bot Chrome User Data directory
        if self.user_data_dir:
            bot_user_data = self.user_data_dir
        else:
            # Default: bot_chrome_data/ in the project root
            project_root = Path(__file__).resolve().parent.parent
            bot_user_data = str(project_root / BOT_USER_DATA_DIR)

        # Original Chrome User Data (for diagnostic display only)
        original_user_data = self._get_default_user_data_dir()

        logger.info("")
        logger.info("=" * 60)
        logger.info("BOT CHROME CONFIGURATION")
        logger.info("=" * 60)
        logger.info("")
        logger.info("  Browser: SYSTEM GOOGLE CHROME")
        logger.info("")
        logger.info(f"  Executable:")
        logger.info(f"    {chrome_path}")
        logger.info("")
        logger.info(f"  Bot User Data:")
        logger.info(f"    {bot_user_data}")
        logger.info("")
        logger.info(f"  Original Chrome User Data:")
        logger.info(f"    {original_user_data}")
        logger.info("")
        logger.info(f"  Bot uses original User Data:  NO")
        logger.info(f"  Bot uses dedicated User Data: YES")
        logger.info("")
        logger.info(f"  CDP port: {CDP_PORT}")
        logger.info("")
        logger.info("=" * 60)

        logger.info("[1] Validating paths...")
        if not Path(chrome_path).exists():
            raise RuntimeError(f"Chrome executable not found: {chrome_path}")
        logger.info(f"[1] Chrome executable: OK ({chrome_path})")

        # -- [2] Ensure bot Chrome User Data exists --
        bot_path = Path(bot_user_data)
        if not bot_path.exists():
            logger.info(f"[2] Creating bot Chrome User Data: {bot_user_data}")
            bot_path.mkdir(parents=True, exist_ok=True)
        else:
            logger.info(f"[2] Bot Chrome User Data exists: {bot_user_data}")

        # Verify it's NOT the same as original
        try:
            bot_resolved = str(bot_path.resolve())
            orig_resolved = str(Path(original_user_data).resolve())
            if bot_resolved == orig_resolved:
                raise RuntimeError(
                    f"CRITICAL: Bot User Data is the SAME as original Chrome User Data!\n"
                    f"  Bot:  {bot_resolved}\n"
                    f"  Orig: {orig_resolved}\n"
                    f"Refusing to continue."
                )
        except OSError:
            pass  # Path may not exist yet, that's OK

        logger.info(f"[2] Bot User Data validated: OK")

        # -- [3] Launch Chrome with bot_chrome_data --
        logger.info("[3] Launching system Chrome...")
        logger.info(f"    Chrome:           {chrome_path}")
        logger.info(f"    --user-data-dir: {bot_user_data}")
        logger.info(f"    --debug-port:    {CDP_PORT}")

        chrome_args = [
            chrome_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={bot_user_data}",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        # Log full command line for verification
        logger.info("[3] Chrome command line:")
        logger.info(f"    {' '.join(chrome_args)}")

        try:
            self._chrome_process = subprocess.Popen(
                chrome_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._bot_chrome_pid = self._chrome_process.pid
        except Exception as e:
            raise RuntimeError(f"Failed to launch Chrome: {e}")

        logger.info(f"[3] Chrome started")
        logger.info(f"    BOT CHROME PID: {self._bot_chrome_pid}")

        # -- [4] Wait for CDP port --
        logger.info("[4] Waiting for Chrome debugging port...")
        port_ready = await self._wait_for_port(CDP_PORT, timeout=20)
        if not port_ready:
            raise RuntimeError(
                f"Chrome did not open debugging port {CDP_PORT} within 20 seconds."
            )
        logger.info(f"[4] CDP port {CDP_PORT} ready [OK]")

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

        # -- [6] List contexts and pages --
        logger.info("[6] Contexts and pages:")
        for ctx_idx, ctx in enumerate(self._browser.contexts):
            logger.info(f"    Context {ctx_idx}: {len(ctx.pages)} page(s)")
            for pg_idx, pg in enumerate(ctx.pages):
                logger.info(f"      Page {pg_idx}: {pg.url}")

        # Get default context
        if not self._browser.contexts:
            self._context = await self._browser.new_context()
        else:
            self._context = self._browser.contexts[0]

        # -- [7] Select working page --
        logger.info("[7] Selecting working page...")
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()
        logger.info(f"[7] Working page: {self._page.url}")

        total_time = time.time() - t0
        logger.info(f"[7] Browser connected ({total_time:.1f}s)")

        return self._page

    async def open_facebook(self) -> bool:
        """Navigate to Facebook homepage and verify it loads."""
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")

        logger.info("[8] Opening Facebook:")
        logger.info("     https://www.facebook.com/")
        logger.info(f"[8] URL before: {self._page.url}")

        try:
            await self._page.goto(
                "https://www.facebook.com/",
                wait_until="load",
                timeout=60000,
            )

            try:
                await self._page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            await asyncio.sleep(3)

            page_url = self._page.url
            doc_url = await self._page.evaluate("window.location.href")
            page_title = await self._page.title()

            logger.info("[8] Verification:")
            logger.info(f"     page.url:          {page_url}")
            logger.info(f"     document.location: {doc_url}")
            logger.info(f"     title:             {page_title}")

            # Screenshot
            try:
                Path("logs").mkdir(exist_ok=True)
                await self._page.screenshot(path="logs/facebook_after_navigation.png")
                logger.info("[8] Screenshot: logs/facebook_after_navigation.png")
            except Exception:
                pass

            if page_url == "about:blank" and doc_url == "about:blank":
                logger.error("[8] CRITICAL: Facebook did NOT load (about:blank)")
                return False

            if "facebook.com" in page_url or "facebook.com" in doc_url:
                logger.info("[8] Facebook loaded successfully.")
                logger.info(f"     WORKING PAGE: {page_url}")
                return True

            logger.warning(f"[8] Unexpected URL: {page_url}")
            return False

        except Exception as e:
            logger.error(f"[8] Failed to open Facebook: {e}")
            return False

    async def stop(self):
        """Disconnect from Chrome and clean up.

        Only terminates the bot's own Chrome process (identified by PID).
        NEVER kills other Chrome instances.
        """
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

        # Only kill our own Chrome process by PID
        if self._chrome_process:
            pid = self._chrome_process.pid
            logger.info(f"Stopping bot Chrome (PID: {pid})...")
            try:
                self._chrome_process.terminate()
                self._chrome_process.wait(timeout=5)
                logger.info(f"Bot Chrome stopped (PID: {pid})")
            except subprocess.TimeoutExpired:
                try:
                    self._chrome_process.kill()
                    logger.info(f"Bot Chrome killed (PID: {pid})")
                except Exception:
                    logger.warning(f"Could not stop bot Chrome (PID: {pid})")
            except Exception:
                try:
                    self._chrome_process.kill()
                except Exception:
                    pass
            self._chrome_process = None
            self._bot_chrome_pid = None

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
                logger.info("[9] Not on Facebook, navigating...")
                if not await self.open_facebook():
                    return False

            logger.info("[9] Checking Facebook authentication...")
            await asyncio.sleep(2)

            current_url = self._page.url
            doc_url = await self._page.evaluate("window.location.href")
            logger.info(f"[9] page.url: {current_url}")
            logger.info(f"[9] document.location.href: {doc_url}")

            # Login form = not authenticated
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
                        logger.warning("[9] Login form detected - NOT authenticated")
                        return False
                except Exception:
                    continue

            # Checkpoint
            checkpoint_selectors = [
                '[data-testid="checkpoint_title"]',
                'div[class*="checkpoint"]',
            ]
            for sel in checkpoint_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        logger.warning("[9] Checkpoint detected")
                        return False
                except Exception:
                    continue

            # Auth indicators
            auth_selectors = [
                '[aria-label="Your profile"]',
                '[aria-label="\u041f\u0440\u043e\u0444\u0456\u043b\u044c"]',
                'svg[aria-label="Your profile"]',
                '[aria-label="Home"]',
                '[aria-label="\u0413\u043e\u043b\u043e\u0432\u043d\u0430"]',
                '[role="feed"]',
                '[data-pagelet="Stories"]',
            ]
            for sel in auth_selectors:
                try:
                    el = await self._page.query_selector(sel)
                    if el:
                        logger.info("[9] Facebook session: AUTHENTICATED")
                        return True
                except Exception:
                    continue

            # URL-based fallback
            url_check = doc_url if doc_url else current_url
            if "facebook.com" in url_check and "/login" not in url_check and "/checkpoint" not in url_check:
                logger.info("[9] Facebook session: AUTHENTICATED (URL-based)")
                return True

            logger.warning("[9] Could not confirm login status")
            logger.info("[9] Facebook session: NOT AUTHENTICATED")
            return False

        except Exception as e:
            logger.error(f"[9] Error checking auth: {e}")
            return False

    async def wait_for_login(self, timeout_minutes: int = 10):
        """Wait for user to log in manually."""
        if not self._page:
            raise RuntimeError("Browser not started.")

        logger.info("=" * 60)
        logger.info("Waiting for Facebook login...")
        logger.info(f"Waiting up to {timeout_minutes} minutes...")
        logger.info("=" * 60)

        timeout_seconds = timeout_minutes * 60
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                if await self.check_facebook_auth():
                    logger.info("Login detected!")
                    return True
            except Exception:
                pass

            await asyncio.sleep(5)
            elapsed += 5

            if elapsed % 30 == 0:
                logger.info(f"Waiting... ({elapsed // 60}m {elapsed % 60}s)")

        logger.error(f"Login timeout after {timeout_minutes} minutes")
        return False

    # -- Helpers --

    @staticmethod
    async def _wait_for_port(port: int, timeout: int = 20) -> bool:
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
        """Get default Chrome user data directory for the platform (for display only)."""
        if sys.platform == "win32":
            return str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
        elif sys.platform == "darwin":
            return str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
        else:
            return str(Path.home() / ".config" / "google-chrome")
