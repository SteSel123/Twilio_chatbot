"""Ensure local platform/ package loads instead of stdlib platform."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_platform_pkg = ROOT / "platform"
if "platform" in sys.modules and not hasattr(sys.modules["platform"], "__path__"):
    del sys.modules["platform"]

if "platform" not in sys.modules or not hasattr(sys.modules.get("platform"), "mcp"):
    _spec = importlib.util.spec_from_file_location(
        "platform",
        _platform_pkg / "__init__.py",
        submodule_search_locations=[str(_platform_pkg)],
    )
    if _spec and _spec.loader:
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["platform"] = _mod
        _spec.loader.exec_module(_mod)
