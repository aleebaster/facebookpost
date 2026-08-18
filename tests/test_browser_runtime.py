"""
Browser runtime diagnostic test.
Checks Chrome executable, User Data, Profile 2, and attempts launch.
Run: python tests/test_browser_runtime.py
"""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser import BrowserManager


async def diagnostic():
    print("=" * 60)
    print("BROWSER RUNTIME DIAGNOSTIC")
    print("=" * 60)

    # [1] Check Chrome executable
    chrome_path = BrowserManager._find_chrome_executable()
    exists = chrome_path and Path(chrome_path).exists()
    print(f"\n[1] Chrome executable: {'FOUND' if exists else 'NOT FOUND'}")
    if exists:
        print(f"    Path: {chrome_path}")
    else:
        print("    FATAL: Cannot proceed without Chrome")
        return

    # [2] Check User Data directory
    user_data = BrowserManager._get_default_user_data_dir()
    ud_exists = Path(user_data).exists()
    print(f"\n[2] User Data directory: {'EXISTS' if ud_exists else 'NOT FOUND'}")
    print(f"    Path: {user_data}")
    if not ud_exists:
        print("    FATAL: Cannot proceed without User Data")
        return

    # [3] Check Profile 2
    profile_path = Path(user_data) / "Profile 2"
    p2_exists = profile_path.exists()
    print(f"\n[3] Profile 2: {'EXISTS' if p2_exists else 'NOT FOUND'}")
    print(f"    Path: {profile_path}")
    if not p2_exists:
        print("    WARNING: Profile 2 does not exist")

    # [4] Check lock files
    locks = BrowserManager._check_lock_files(user_data)
    print(f"\n[4] Lock files: {locks}")

    # [5] Check Chrome process
    chrome_running = BrowserManager._is_chrome_running()
    print(f"\n[5] Chrome process: {'RUNNING' if chrome_running else 'NOT RUNNING'}")

    if chrome_running:
        print("\n    FATAL: Chrome is running. Close ALL Chrome windows first.")
        return

    # [6] Attempt browser launch
    print(f"\n[6] Attempting browser launch...")
    browser = BrowserManager(
        user_data_dir=user_data,
        profile_name="Profile 2",
        chrome_binary=chrome_path,
    )

    try:
        t0 = time.time()
        page = await browser.start()
        elapsed = time.time() - t0
        print(f"    Browser started in {elapsed:.1f}s")

        # [7] Check page URL
        print(f"\n[7] Page URL after start: {page.url}")

        # [8] Navigate to Facebook
        print(f"\n[8] Navigating to Facebook...")
        success = await browser.open_facebook()
        print(f"    Result: {'SUCCESS' if success else 'FAILED'}")
        print(f"    Current URL: {page.url}")

        # [9] Check auth
        print(f"\n[9] Checking Facebook auth...")
        auth = await browser.check_facebook_auth()
        print(f"    Authenticated: {'YES' if auth else 'NO'}")

        await browser.stop()
        print(f"\n[10] Browser stopped cleanly")

    except Exception as e:
        print(f"\n    ERROR: {e}")
        try:
            await browser.stop()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(diagnostic())
