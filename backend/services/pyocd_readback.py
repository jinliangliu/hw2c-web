"""Read target flash via pyocd's Python API into a caller-owned file.

pyocd CLI's ``savemem`` lowercases and strips underscores from paths on this
machine and then rejects them as invalid, so no path crosses its command line.
The MCP service passes the output path as a plain argparse argument to *this*
script instead.  The target is left halted (no implicit reset).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from pyocd.core.helpers import ConnectHelper

CHUNK = 4096


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--address", required=True, type=lambda value: int(value, 0))
    parser.add_argument("--length", required=True, type=int)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if args.length <= 0:
        parser.error("--length must be positive")

    session = ConnectHelper.session_with_chosen_probe(target_override=args.target)
    if session is None:
        print("no debug probe found", file=__import__("sys").stderr)
        return 2
    session.open()
    try:
        target = session.target
        target.halt()
        data = bytearray()
        for offset in range(0, args.length, CHUNK):
            size = min(CHUNK, args.length - offset)
            data += bytes(target.read_memory_block8(args.address + offset, size))
        target.halt()
    finally:
        session.close()
    Path(args.out).write_bytes(bytes(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
