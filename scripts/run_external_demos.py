#!/usr/bin/env python3
"""Run external Board + Pulse demos (Modoor must be reachable)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("MODOOR_URL", "http://127.0.0.1:8765")
    env.setdefault("PYTHONPATH", str(ROOT))
    procs: list[subprocess.Popen] = []
    cmd_base = [sys.executable, "-m"]
    try:
        for mod in ("external.board", "external.pulse"):
            p = subprocess.Popen(cmd_base + [mod], cwd=str(ROOT), env=env)
            procs.append(p)
            print(f"started {mod} pid={p.pid}")
        print("Board  http://127.0.0.1:8771/")
        print("Pulse  http://127.0.0.1:8772/")
        print("Ctrl+C to stop")
        while True:
            for p in procs:
                code = p.poll()
                if code is not None:
                    print(f"process exited: {p.args} code={code}")
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping…")
        return 0
    finally:
        for p in procs:
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
