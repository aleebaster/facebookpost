"""
Browser management module.

Chrome 151 blocks remote debugging (both --remote-debugging-port and
--remote-debugging-pipe) when used with the DEFAULT User Data directory.
Error: "DevTools remote debugging requires a non-default data directory."

Solution: Create a directory junction from chrome_user_data -> original User Data.
Chrome sees it as "non-default" and allows remote debugging.
The junction points to the EXACT SAME files, so the original Profile 2
and Facebook session are preserved.

Architecture:
  Python -> Playwright CDP client -> System Google Chrome -> junction -> original User Data/Profile 2

IMPORTANT: Chrome must be CLOSED before running the bot.
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

# Junction directory name (points to original User Data)
JUNCTION_DIR = "chrome_user_data"


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
        Launch system Chrome with Profile 2 via CDP.

        Steps:
          [1] Validate paths
          [2] Create junction to original User Data
          [3] Launch Chrome with junction + CDP
          [4] Connect Playwright via CDP
          [5] Select working page
          [6] Navigate to Facebook
        """
        t0 = time.time()

        # -- [1] Resolve and validate paths --
        chrome_path = self.chrome_binary or self._find_chrome_executable()
        user_data = self.user_data_dir or self._get_default_user_data_dir()
        profile_path = Path(user_data) / self.profile_name

        logger.info("=" * 60)
        logger.info("BROWSER CONFIGURATION")
        logger.info("=" * 60)
        logger.info("Browser: SYSTEM GOOGLE CHROME")
        logger.info(f"  Executable:     {chrome_path}")
        logger.info(f"  Original User:  {user_data}")
        logger.info(f"  Original Profile: {profile_path}")
        logger.info(f"  CDP port:       {CDP_PORT}")
        logger.info("=" * 60)

        logger.info("[1] Validating paths...")
        if not Path(chrome_path).exists():
            raise RuntimeError(f"Chrome executable not found: {chrome_path}")
        if not Path(user_data).exists():
            raise RuntimeError(f"User Data directory not found: {user_data}")
        if not profile_path.exists():
            raise RuntimeError(f"Profile not found: {profile_path}")
        logger.info("[1] All paths validated [OK]")

        # -- [2] Create junction to original User Data --
        # IMPORTANT: Do NOT use .resolve() — it follows the junction and returns the target.
        # Use the literal path string so Chrome sees it as "non-default".
        project_root = Path(__file__).resolve().parent.parent  # facebookpost/
        junction_path = project_root / JUNCTION_DIR
        junction_path_str = str(junction_path)  # keep as string, do NOT resolve
        target_path_str = str(Path(user_data).resolve())

        logger.info("[2] Creating junction to original User Data...")
        logger.info(f"    Junction: {junction_path_str}")
        logger.info(f"    Target:   {target_path_str}")

        # CRITICAL: junction path MUST differ from target
        if junction_path_str == target_path_str or junction_path_str == user_data:
            raise RuntimeError(
                f"CRITICAL: Junction path and target are identical!\n"
                f"  Junction: {junction_path_str}\n"
                f"  Target:   {target_path_str}\n"
                f"Refusing to continue."
            )

        # Remove old junction if exists
        if junction_path.exists():
            try:
                junction_path.rmdir()
            except Exception:
                pass

        # Remove stale directory if it exists (not a junction)
        if junction_path.is_dir() and not junction_path.is_symlink():
            import shutil
            shutil.rmtree(junction_path, ignore_errors=True)

        # Create junction using Windows mklink /J
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", junction_path_str, user_data],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if not junction_path.exists():
            raise RuntimeError(
                f"Failed to create junction from {junction_path_str} to {user_data}\n"
                f"cmd output: {result.stdout} {result.stderr}"
            )

        # Verify junction works
        entries = list(junction_path.iterdir())
        resolved_target = str(junction_path.resolve())
        logger.info(f"[2] Junction created: {len(entries)} entries")
        logger.info(f"[2] Resolved target: {resolved_target}")
        logger.info(f"[2] Profile 2 accessible: {(junction_path / self.profile_name).exists()}")
        if resolved_target != target_path_str:
            logger.warning(f"[2] Junction resolves to different path! Expected: {target_path_str}")

        # -- [3] Launch Chrome with junction --
        logger.info("[3] Launching system Chrome...")
        logger.info(f"    Chrome:          {chrome_path}")
        logger.info(f"    --user-data-dir={junction_path_str}")
        logger.info(f"    --profile-dir=  {self.profile_name}")
        logger.info(f"    --debug-port=   {CDP_PORT}")

        chrome_args = [
            chrome_path,
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={junction_path_str}",
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

        # -- [4] Wait for CDP port --
        logger.info("[4] Waiting for Chrome debugging port...")
        port_ready = await self._wait_for_port(CDP_PORT, timeout=20)
        if not port_ready:
            raise RuntimeError(
                f"Chrome did not open debugging port {CDP_PORT} within 20 seconds."
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
        """Get default Chrome user data directory for the platform."""
        if sys.platform == "win32":
            return str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data")
        elif sys.platform == "darwin":
            return str(Path.home() / "Library" / "Application Support" / "Google" / "Chrome")
        else:
            return str(Path.home() / ".config" / "google-chrome")
