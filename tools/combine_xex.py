#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def iter_segments(path: Path):
    data = path.read_bytes()
    offset = 0
    if data.startswith(b"\xff\xff"):
        offset = 2
    while offset < len(data):
        if offset + 4 > len(data):
            raise ValueError(f"{path}: truncated segment header at offset {offset}")
        start = data[offset] | (data[offset + 1] << 8)
        end = data[offset + 2] | (data[offset + 3] << 8)
        offset += 4
        if start == 0xFFFF:
            continue
        if end < start:
            raise ValueError(f"{path}: invalid segment ${start:04X}-${end:04X}")
        size = end - start + 1
        payload = data[offset : offset + size]
        if len(payload) != size:
            raise ValueError(f"{path}: truncated segment ${start:04X}-${end:04X}")
        offset += size
        yield start, end, payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Combine Atari XEX/OBX files into one XEX."
    )
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("inputs", nargs="+")
    args = parser.parse_args()

    out = bytearray(b"\xff\xff")
    for name in args.inputs:
        for start, end, payload in iter_segments(Path(name)):
            out.extend((start & 0xFF, start >> 8, end & 0xFF, end >> 8))
            out.extend(payload)

    Path(args.output).write_bytes(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
