from __future__ import annotations

import subprocess
import sys


HOT_RELOAD_EXIT_CODE = 75


def main() -> int:
    while True:
        result = subprocess.run([sys.executable, "-m", "audio_playground"], check=False)
        if result.returncode != HOT_RELOAD_EXIT_CODE:
            return result.returncode
        print("Source changed. Restarting AI Audio Playground…", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
