#!/usr/bin/env python3
"""Export the art currently assembled into the game source, for the tile editor."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from charsetter import CharsetterError, build_project, extract_source_art


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "atari8-client" / "fujirealm.asm"
DEFAULT_BASE = REPO_ROOT / "atari8-client" / "art" / "fujirealm_charsetter"


def write(path: Path, data: bytes, force: bool) -> None:
    if path.exists() and not force:
        raise CharsetterError(f"refusing to overwrite {path}; pass --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--project", type=Path, default=DEFAULT_BASE.with_suffix(".json"))
    parser.add_argument("--font", type=Path, default=DEFAULT_BASE.with_suffix(".fnt"))
    parser.add_argument("--force", action="store_true", help="replace existing editable assets")
    args = parser.parse_args()

    try:
        font, tiles, sprites, palette = extract_source_art(args.source)
        project = build_project(font, tiles, sprites, palette)
        encoded = (json.dumps(project, indent=2) + "\n").encode("ascii")
        write(args.project, encoded, args.force)
        write(args.font, bytes(project["fontData"]), args.force)
        print(f"exported {len(font)} font bytes, {len(tiles[0])} tiles, and {len(sprites[0])} player frames")
        print(f"  project: {args.project}")
        print(f"  font:    {args.font}")
        return 0
    except (OSError, CharsetterError, json.JSONDecodeError) as exc:
        print(f"export_charsetter.py: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
