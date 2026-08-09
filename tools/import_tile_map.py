#!/usr/bin/env python3
"""Import an EnvisionPC tile-mode .map file as FujiRealm MADS art."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "atari8-client" / "fujirealm.asm"
DEFAULT_INPUT = REPO_ROOT / "atari8-client" / "art" / "fujirealm_tiles.map"
DEFAULT_OUTPUT = REPO_ROOT / "atari8-client" / "generated" / "fujirealm_art.inc"

FONT_BYTES = 1024
ANTIC_MODE = 4
TILE_W = 2
TILE_H = 2
TABLE_NAMES = ("tile2x2_tl", "tile2x2_tr", "tile2x2_bl", "tile2x2_br")


class ImportErrorWithContext(RuntimeError):
    pass


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def load_asm(path: Path, seen: set[Path] | None = None) -> list[tuple[Path, int, str]]:
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        raise ImportErrorWithContext(f"recursive include detected: {path}")
    seen.add(path)

    result: list[tuple[Path, int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ImportErrorWithContext(f"source file not found: {path}") from exc

    for lineno, line in enumerate(lines, 1):
        clean = strip_comment(line)
        match = re.match(r'^\s*icl\s+"([^"]+)"\s*$', clean, re.IGNORECASE)
        if match:
            result.extend(load_asm((path.parent / match.group(1)).resolve(), seen))
        else:
            result.append((path, lineno, line.rstrip("\n")))
    seen.remove(path)
    return result


def normalize_expr(expr: str) -> str:
    expr = re.sub(r"\$([0-9A-Fa-f]+)", lambda m: "0x" + m.group(1), expr)
    expr = re.sub(r"%([01]+)", lambda m: "0b" + m.group(1), expr)
    return expr


def eval_expr(expr: str, constants: dict[str, int], where: str) -> int:
    expr = normalize_expr(expr.strip())
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ImportErrorWithContext(f"{where}: cannot parse expression {expr!r}") from exc

    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return int(node.value)
        if isinstance(node, ast.Name):
            if node.id not in constants:
                raise ImportErrorWithContext(f"{where}: unknown symbol {node.id!r} in {expr!r}")
            return constants[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -walk(node.operand)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
            return walk(node.operand)
        if isinstance(node, ast.BinOp):
            left = walk(node.left)
            right = walk(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
        raise ImportErrorWithContext(f"{where}: unsupported expression {expr!r}")

    return walk(tree)


def parse_constants(lines: list[tuple[Path, int, str]]) -> dict[str, int]:
    constants: dict[str, int] = {}
    pending: list[tuple[str, str, str]] = []
    for path, lineno, raw in lines:
        clean = strip_comment(raw)
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", clean)
        if match:
            pending.append((match.group(1), match.group(2).strip(), f"{path}:{lineno}"))

    changed = True
    while pending and changed:
        changed = False
        remaining: list[tuple[str, str, str]] = []
        for name, expr, where in pending:
            try:
                constants[name] = eval_expr(expr, constants, where)
                changed = True
            except ImportErrorWithContext as exc:
                if "unknown symbol" in str(exc):
                    remaining.append((name, expr, where))
                else:
                    raise
        pending = remaining

    if pending:
        name, expr, where = pending[0]
        raise ImportErrorWithContext(f"{where}: cannot resolve constant {name} = {expr}")
    return constants


def is_label_line(clean: str) -> bool:
    if not clean or clean.startswith(":"):
        return False
    if "=" in clean:
        return False
    if re.match(r"^(dta|org|run|icl)\b", clean, re.IGNORECASE):
        return False
    return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*$", clean))


def split_values(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_dta_line(clean: str, constants: dict[str, int], where: str) -> list[int]:
    repeat_match = re.match(r"^:(.+?)\s+dta\s+(.+)$", clean, re.IGNORECASE)
    if repeat_match:
        count = eval_expr(repeat_match.group(1), constants, where)
        values = parse_dta_values(repeat_match.group(2), constants, where)
        return values * count
    match = re.match(r"^dta\s+(.+)$", clean, re.IGNORECASE)
    if not match:
        return []
    return parse_dta_values(match.group(1), constants, where)


def parse_dta_values(text: str, constants: dict[str, int], where: str) -> list[int]:
    values = []
    for expr in split_values(text):
        value = eval_expr(expr, constants, where)
        if not 0 <= value <= 255:
            raise ImportErrorWithContext(f"{where}: byte value out of range: {expr} -> {value}")
        values.append(value)
    return values


def find_label(lines: list[tuple[Path, int, str]], label: str) -> int:
    for index, (_, _, raw) in enumerate(lines):
        if strip_comment(raw) == label:
            return index
    raise ImportErrorWithContext(f"label not found: {label}")


def parse_table(lines: list[tuple[Path, int, str]], constants: dict[str, int], label: str) -> list[int]:
    start = find_label(lines, label) + 1
    values: list[int] = []
    for path, lineno, raw in lines[start:]:
        clean = strip_comment(raw)
        if not clean:
            continue
        if is_label_line(clean) or re.match(r"^org\b", clean, re.IGNORECASE):
            break
        values.extend(parse_dta_line(clean, constants, f"{path}:{lineno}"))
    if not values:
        raise ImportErrorWithContext(f"{label}: table is empty")
    return values


def required_tile_count(source: Path) -> int:
    lines = load_asm(source)
    constants = parse_constants(lines)
    tables = [parse_table(lines, constants, name) for name in TABLE_NAMES]
    lengths = {len(table) for table in tables}
    if len(lengths) != 1:
        detail = ", ".join(f"{name}={len(table)}" for name, table in zip(TABLE_NAMES, tables))
        raise ImportErrorWithContext(f"tile table lengths differ: {detail}")
    return lengths.pop()


def read_le16(data: bytes, offset: int, name: str) -> tuple[int, int]:
    if offset + 2 > len(data):
        raise ImportErrorWithContext(f"truncated while reading {name}")
    return data[offset] | (data[offset + 1] << 8), offset + 2


def parse_map(path: Path, required_tiles: int) -> tuple[list[int], list[list[int]], int, int]:
    data = path.read_bytes()
    offset = 0
    if len(data) < 1 + 2 + 2 + 5:
        raise ImportErrorWithContext("file is too short for EnvisionPC map header")

    mode = data[offset]
    offset += 1
    if mode != ANTIC_MODE:
        raise ImportErrorWithContext(f"ANTIC mode must be {ANTIC_MODE}, found {mode}")

    map_w, offset = read_le16(data, offset, "map width")
    map_h, offset = read_le16(data, offset, "map height")
    offset += 5

    map_bytes = map_w * map_h
    if offset + map_bytes > len(data):
        raise ImportErrorWithContext("map data is truncated")
    offset += map_bytes

    if offset + FONT_BYTES > len(data):
        raise ImportErrorWithContext(f"font data is truncated; expected {FONT_BYTES} bytes")
    font = list(data[offset : offset + FONT_BYTES])
    offset += FONT_BYTES
    if len(font) != FONT_BYTES:
        raise ImportErrorWithContext(f"font data must be exactly {FONT_BYTES} bytes")

    if offset >= len(data):
        raise ImportErrorWithContext("missing tile-map block")
    block_type = data[offset]
    offset += 1
    if block_type != 1:
        raise ImportErrorWithContext(f"tile block type must be 1, found {block_type}")

    tile_w, offset = read_le16(data, offset, "tile width")
    tile_h, offset = read_le16(data, offset, "tile height")
    tile_count_minus_one, offset = read_le16(data, offset, "tile count")
    tile_count = tile_count_minus_one + 1
    if tile_w != TILE_W:
        raise ImportErrorWithContext(f"tile width must be {TILE_W}, found {tile_w}")
    if tile_h != TILE_H:
        raise ImportErrorWithContext(f"tile height must be {TILE_H}, found {tile_h}")
    if tile_count < required_tiles:
        raise ImportErrorWithContext(
            f"tile count {tile_count} is smaller than required game tile count {required_tiles}"
        )

    bytes_per_tile = tile_w * tile_h
    needed = tile_count * bytes_per_tile
    if offset + needed > len(data):
        raise ImportErrorWithContext(
            f"tile data is truncated; expected {needed} bytes, found {len(data) - offset}"
        )

    raw_tiles = data[offset : offset + needed]
    tables = [[], [], [], []]
    for tile_id in range(required_tiles):
        base = tile_id * bytes_per_tile
        tables[0].append(raw_tiles[base])
        tables[1].append(raw_tiles[base + 1])
        tables[2].append(raw_tiles[base + 2])
        tables[3].append(raw_tiles[base + 3])

    return font, tables, map_w, map_h


def fmt_hex(value: int) -> str:
    return f"${value:02X}"


def emit_dta(lines: list[str], values: list[int], per_line: int = 16) -> None:
    for index in range(0, len(values), per_line):
        chunk = values[index : index + per_line]
        lines.append("        dta " + ",".join(fmt_hex(value) for value in chunk))


def generate_include(font: list[int], tables: list[list[int]], source_map: Path) -> str:
    if not font or any(not table for table in tables):
        raise ImportErrorWithContext("output include would be empty or malformed")

    lines: list[str] = [
        "; Generated by tools/import_tile_map.py",
        f"; Source map: {source_map}",
        "; Edit the EnvisionPC .map, then regenerate this file.",
        "",
        "; Logical tile 2x2 mapping:",
        "; byte order in each tile: top-left, top-right, bottom-left, bottom-right.",
    ]
    for name, table in zip(TABLE_NAMES, tables):
        lines.append(f"{name}")
        emit_dta(lines, table)
    lines.extend(["", "        org FONT", "font_data"])
    emit_dta(lines, font)
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("art_file", nargs="?", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        count = required_tile_count(args.source)
        font, tables, map_w, map_h = parse_map(args.art_file, count)
        include = generate_include(font, tables, args.art_file)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(include, encoding="utf-8")
        print(
            f"imported {len(font)} font bytes and {count} logical tiles "
            f"from {args.art_file} ({map_w}x{map_h} reference map) to {args.output}"
        )
        return 0
    except (OSError, ImportErrorWithContext) as exc:
        print(f"import_tile_map.py: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
