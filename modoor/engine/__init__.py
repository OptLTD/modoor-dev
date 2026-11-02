"""Schema-driven record engine (worth-compatible wire format)."""

from modoor.engine.service import EngineService, get_engine

# Register BaseSerial on Base.metadata before init_db / create_all.
from modoor.engine.serial import BaseSerial as BaseSerial  # noqa: E402, F401

__all__ = ["EngineService", "get_engine", "BaseSerial"]
