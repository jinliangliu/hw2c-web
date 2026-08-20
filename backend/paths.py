"""Resolve the sibling hw2c project root.

The web backend expects the core ``hw2c`` repository to be available on
disk. Local development keeps it as a sibling directory; CI can checkout
``hw2c`` inside the web workspace instead. Prefer an explicit
``HW2C_ROOT`` environment variable, then the sibling layout, then the
vendored/in-workspace layout.
"""

from __future__ import annotations

import os
from pathlib import Path


def get_hw2c_root() -> Path:
    """Return the resolved path to the hw2c repository."""
    explicit = os.environ.get("HW2C_ROOT")
    if explicit:
        return Path(explicit).resolve()

    backend_dir = Path(__file__).resolve().parent
    web_root = backend_dir.parent
    candidates = (
        web_root.parent / "hw2c",  # local sibling layout
        web_root / "hw2c",         # CI/in-workspace layout
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
