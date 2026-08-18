"""
Runtime diagnostic test for browser configuration.
Verifies Chrome executable, User Data, Profile 2, and optionally CDP connection.
"""
import asyncio
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def check_chrome_process():
    """Check if Chrome is running."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and "chrome.exe" in line.lower():
                parts = line.split()
                if parts and parts[0].lower() == "chrome.exe":
                    return True
        return False
    except Exception:
        return False


def main():
    print("=" * 60)
    print("BROWSER RUNTIME DIAGNOSTIC")
    print("=" * 60)

    # 1. Chrome executable
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    chrome_exists = Path(chrome_path).exists()
    print(f"\n[1] Chrome executable:")
    print(f"    Path: {chrome_path}")
    print(f"    Exists: {'YES' if chrome_exists else 'NO'}")

    # 2. User Data
    user_data = r"C:\Users\andre\AppData\Local\Google\Chrome\User Data"
    user_data_exists = Path(user_data).exists()
    print(f"\n[2] User Data directory:")
    print(f"    Path: {user_data}")
    print(f"    Exists: {'YES' if user_data_exists else 'NO'}")

    # 3. Profile 2
    profile_path = Path(user_data) / "Profile 2"
    profile_exists = profile_path.exists()
    print(f"\n[3] Profile 2:")
    print(f"    Path: {profile_path}")
    print(f"    Exists: {'YES' if profile_exists else 'NO'}")

    # 4. Chrome process
    chrome_running = check_chrome_process()
    print(f"\n[4] Chrome process:")
    print(f"    Running: {'YES' if chrome_running else 'NO'}")

    # 5. Lock files
    singleton_lock = Path(user_data) / "SingletonLock"
    lockfile = Path(user_data) / "lockfile"
    print(f"\n[5] Lock files:")
    print(f"    SingletonLock exists: {'YES' if singleton_lock.exists() else 'NO'}")
    print(f"    lockfile exists: {'YES' if lockfile.exists() else 'NO'}")

    # 6. CDP connection test
    print(f"\n[6] CDP connection test:")

    if chrome_running:
        print("    SKIP - Chrome is running (close Chrome to test)")
        print("    The bot will launch its own Chrome instance.")
    else:
        print("    Chrome is NOT running.")
        print("    The bot should be able to launch Chrome with Profile 2.")
        print(f"\n    To test the full flow, run:")
        print(f"    python -m src.main --mode DRY_RUN")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    all_ok = chrome_exists and user_data_exists and profile_exists
    print(f"Chrome executable:  {'OK' if chrome_exists else 'MISSING'}")
    print(f"User Data:          {'OK' if user_data_exists else 'MISSING'}")
    print(f"Profile 2:          {'OK' if profile_exists else 'MISSING'}")
    print(f"Chrome running:     {'YES (close to test)' if chrome_running else 'NO'}")

    if all_ok and not chrome_running:
        print(f"\nREADY: Close Chrome and run:")
        print(f"  python -m src.main --mode DRY_RUN")
    elif all_ok and chrome_running:
        print(f"\nREADY (after closing Chrome):")
        print(f"  1. Close all Chrome windows")
        print(f"  2. python -m src.main --mode DRY_RUN")
    else:
        print(f"\nNOT READY: Fix missing paths above")

    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
