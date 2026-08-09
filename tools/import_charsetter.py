#!/usr/bin/env python3
"""Validate or import a FujiRealm Charsetter project into MADS art data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from charsetter import CharsetterError, generate_include, validate_project


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = REPO_ROOT / "atari8-client" / "art" / "fujirealm_charsetter.json"
DEFAULT_OUTPUT = REPO_ROOT / "atari8-client" / "generated" / "fujirealm_art.inc"


def optional_bytes(path: Path | None) -> bytes | None:
    return path.read_bytes() if path is not None else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", type=Path, default=DEFAULT_PROJECT)
    parser.add_argument("--font", type=Path, help="override project fontData with a Charsetter .fnt")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="validate without writing the assembly include")
    args = parser.parse_args()

    try:
        project = json.loads(args.project.read_text(encoding="utf-8"))
        font, tiles, sprites = validate_project(project, font_override=optional_bytes(args.font))
        if args.check:
            print(f"validated {args.project}: {len(font)} font bytes, {len(tiles[0])} tiles, {len(sprites[0])} player frames")
            return 0
        include = generate_include(font, tiles, sprites, args.project)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(include, encoding="ascii")
        temporary.replace(args.output)
        print(f"imported {args.project} to {args.output}")
        return 0
    except (OSError, CharsetterError, json.JSONDecodeError) as exc:
        print(f"import_charsetter.py: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
