"""Runtime diagnostic test for browser configuration."""

import asyncio
import subprocess
import sys
import time
from pathlib import Path

from src.browser import BrowserManager, CDP_PORT, JUNCTION_DIR


def test_chrome_diagnostic():
    """Print diagnostic info about Chrome configuration."""
    bm = BrowserManager()
    project_root = Path(__file__).resolve().parent.parent
    junction_path = project_root / JUNCTION_DIR
    target_path = bm._get_default_user_data_dir()

    print("\n" + "=" * 60)
    print("CHROME DIAGNOSTIC")
    print("=" * 60)

    chrome = bm._find_chrome_executable()
    print(f"\n[1] Chrome executable: {chrome}")
    print(f"    Exists: {Path(chrome).exists() if chrome else 'N/A'}")

    print(f"\n[2] Original User Data: {target_path}")
    print(f"    Exists: {Path(target_path).exists()}")

    profile_path = Path(target_path) / bm.profile_name
    print(f"    Profile 2: {profile_path}")
    print(f"    Exists: {profile_path.exists()}")

    print(f"\n[3] Junction path: {str(junction_path)}")
    print(f"    Junction target: {target_path}")

    # Critical check: junction path != target path
    junction_str = str(junction_path)
    target_str = str(Path(target_path).resolve())
    print(f"    Junction == Target: {junction_str == target_str}")
    if junction_str == target_str:
        print("    *** BUG: Junction and target are identical! ***")
    else:
        print(f"    OK: Junction ({junction_str}) != Target ({target_str})")

    print(f"\n[4] CDP port: {CDP_PORT}")

    print(f"\n[5] Chrome running:")
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq chrome.exe"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [l for l in result.stdout.split("\n") if "chrome.exe" in l.lower()]
        print(f"    Processes: {len(lines)}")
        for line in lines[:5]:
            print(f"      {line.strip()}")
    except Exception as e:
        print(f"    Error: {e}")

    print("\n" + "=" * 60)
    print("TO TEST:")
    print("  1. Close ALL Chrome windows")
    print("  2. Run: python -m src.main --mode DRY_RUN")
    print("=" * 60)


if __name__ == "__main__":
    test_chrome_diagnostic()
