"""hw2c-local Connector entry point: python -m hw2c_connector.local."""

from __future__ import annotations

import sys
from pathlib import Path

# cwd is backend/ per connector-meta.json, but make the entry point robust when
# launched from elsewhere (e.g. a smoke test).
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from mcp_server.server import main  # noqa: E402


if __name__ == "__main__":
    main()
