"""Install optional doc packages into MODOOR_PY_CACHE on first use."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import threading
from pathlib import Path

_LOCK = threading.Lock()

OFFICE_PACKAGES = (
    "python-docx>=1.1",
    "python-pptx>=1.0",
    "openpyxl>=3.1",
    "xlrd>=1.2.0,<2",
    "olefile>=0.47",
)
OFFICE_MODULES = ("docx", "pptx", "openpyxl", "xlrd", "olefile")


def cache_dir() -> Path:
    return Path(os.environ.get("MODOOR_PY_CACHE") or "/var/cache/modoor/py")


def activate_cache() -> None:
    path = cache_dir()
    text = str(path)
    if path.is_dir() and text not in sys.path:
        sys.path.insert(0, text)


def _missing(modules: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for name in modules:
        try:
            importlib.import_module(name)
        except ImportError:
            missing.append(name)
    return missing


def ensure_packages(requirements: tuple[str, ...], modules: tuple[str, ...]) -> None:
    activate_cache()
    if not _missing(modules):
        return
    with _LOCK:
        activate_cache()
        if not _missing(modules):
            return
        path = cache_dir()
        path.mkdir(parents=True, exist_ok=True)
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--target",
                text,
                *requirements,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        importlib.invalidate_caches()
        if proc.returncode != 0 or _missing(modules):
            detail = (proc.stderr or proc.stdout or "pip install failed").strip()
            raise RuntimeError(detail[-2000:])


def ensure_office() -> None:
    ensure_packages(OFFICE_PACKAGES, OFFICE_MODULES)
