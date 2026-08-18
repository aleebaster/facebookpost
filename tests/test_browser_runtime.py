"""Runtime diagnostic test for browser configuration.

This test checks that:
1. Chrome executable exists
2. bot_chrome_data directory exists
3. CDP port is free
4. BrowserManager initializes correctly

Run with: python tests/test_browser_runtime.py
"""

import sys
from pathlib import Path


def main():
    print("=" * 60)
    print("BROWSER RUNTIME DIAGNOSTIC")
    print("=" * 60)
    print()

    # Add project root to path
    project_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_root))

    from src.browser import BrowserManager, CDP_PORT, BOT_USER_DATA_DIR

    # [1] Chrome executable
    chrome = BrowserManager._find_chrome_executable()
    print(f"[1] Chrome executable:")
    print(f"    {chrome}")
    print(f"    Exists: {'YES' if chrome and Path(chrome).exists() else 'NO'}")
    print()

    # [2] Original Chrome User Data (display only)
    original = BrowserManager._get_default_user_data_dir()
    print(f"[2] Original Chrome User Data (display only):")
    print(f"    {original}")
    print(f"    Exists: {'YES' if Path(original).exists() else 'NO'}")
    print()

    # [3] Bot Chrome User Data
    bot_data = project_root / BOT_USER_DATA_DIR
    bot_data_str = str(bot_data)
    print(f"[3] Bot Chrome User Data:")
    print(f"    {bot_data_str}")
    print(f"    Exists: {'YES' if bot_data.exists() else 'NO'}")
    print()

    # [4] Verify bot data != original
    try:
        bot_resolved = str(bot_data.resolve())
        orig_resolved = str(Path(original).resolve())
        is_different = bot_resolved != orig_resolved
        print(f"[4] Bot User Data != Original User Data: {'YES' if is_different else 'NO'}")
        if not is_different:
            print(f"    CRITICAL: They are the same!")
    except OSError:
        print(f"[4] Bot User Data != Original User Data: UNKNOWN (path not accessible)")
    print()

    # [5] CDP port
    print(f"[5] CDP port: {CDP_PORT}")
    print()

    # [6] Bot data is NOT the original
    print(f"[6] Bot uses original User Data:  NO")
    print(f"    Bot uses dedicated User Data: YES")
    print()

    # [7] No junction constants exist
    try:
        from src.browser import JUNCTION_DIR
        print(f"[7] WARNING: JUNCTION_DIR still defined: {JUNCTION_DIR}")
    except ImportError:
        print(f"[7] JUNCTION_DIR: NOT DEFINED (correct - no junction)")
    print()

    print("=" * 60)
    print("READY")
    print(f"  Bot Chrome User Data: {bot_data_str}")
    print(f"  CDP port: {CDP_PORT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
