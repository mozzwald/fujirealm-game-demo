#!/usr/bin/env python3
"""Export FujiRealm art to an EnvisionPC tile-mode .map file."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "atari8-client" / "fujirealm.asm"
DEFAULT_OUTPUT = REPO_ROOT / "atari8-client" / "art" / "fujirealm_tiles.map"

FONT_BYTES = 1024
MAP_W = 16
MAP_H = 16
ANTIC_MODE = 4
TILE_W = 2
TILE_H = 2
EXPORT_TILE_COUNT = 256
TABLE_NAMES = ("tile2x2_tl", "tile2x2_tr", "tile2x2_bl", "tile2x2_br")


class ParseError(RuntimeError):
    pass


def strip_comment(line: str) -> str:
    return line.split(";", 1)[0].strip()


def load_asm(path: Path, seen: set[Path] | None = None) -> list[tuple[Path, int, str]]:
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        raise ParseError(f"recursive include detected: {path}")
    seen.add(path)

    result: list[tuple[Path, int, str]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ParseError(f"source file not found: {path}") from exc

    for lineno, line in enumerate(lines, 1):
        clean = strip_comment(line)
        match = re.match(r'^\s*icl\s+"([^"]+)"\s*$', clean, re.IGNORECASE)
        if match:
            include_path = (path.parent / match.group(1)).resolve()
            result.extend(load_asm(include_path, seen))
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
        raise ParseError(f"{where}: cannot parse expression {expr!r}") from exc

    def walk(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return int(node.value)
        if isinstance(node, ast.Name):
            if node.id not in constants:
                raise ParseError(f"{where}: unknown symbol {node.id!r} in {expr!r}")
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
        raise ParseError(f"{where}: unsupported expression {expr!r}")

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
            except ParseError as exc:
                if "unknown symbol" in str(exc):
                    remaining.append((name, expr, where))
                else:
                    raise
        pending = remaining

    if pending:
        name, expr, where = pending[0]
        raise ParseError(f"{where}: cannot resolve constant {name} = {expr}")
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
        if count < 0:
            raise ParseError(f"{where}: negative repeat count")
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
            raise ParseError(f"{where}: byte value out of range: {expr} -> {value}")
        values.append(value)
    return values


def find_label(lines: list[tuple[Path, int, str]], label: str) -> int:
    for index, (_, _, raw) in enumerate(lines):
        if strip_comment(raw) == label:
            return index
    raise ParseError(f"label not found: {label}")


def parse_table(lines: list[tuple[Path, int, str]], constants: dict[str, int], label: str) -> list[int]:
    start = find_label(lines, label) + 1
    values: list[int] = []
    for path, lineno, raw in lines[start:]:
        clean = strip_comment(raw)
        if not clean:
            continue
        if is_label_line(clean) or re.match(r"^org\b", clean, re.IGNORECASE):
            break
        parsed = parse_dta_line(clean, constants, f"{path}:{lineno}")
        if parsed:
            values.extend(parsed)
    if not values:
        raise ParseError(f"{label}: table is empty")
    return values


def parse_font(lines: list[tuple[Path, int, str]], constants: dict[str, int]) -> list[int]:
    start = find_label(lines, "font_data") + 1
    values: list[int] = []
    for path, lineno, raw in lines[start:]:
        clean = strip_comment(raw)
        if not clean:
            continue
        if is_label_line(clean) or re.match(r"^(org|run)\b", clean, re.IGNORECASE):
            break
        parsed = parse_dta_line(clean, constants, f"{path}:{lineno}")
        if parsed:
            values.extend(parsed)
            if len(values) >= FONT_BYTES:
                break
    if len(values) != FONT_BYTES:
        raise ParseError(f"font_data must contain exactly {FONT_BYTES} bytes, found {len(values)}")
    return values


def parse_game_palette(lines: list[tuple[Path, int, str]], constants: dict[str, int]) -> list[int]:
    index = find_label(lines, "set_game_palette")
    colors: dict[str, int] = {}
    last_lda: int | None = None
    for path, lineno, raw in lines[index + 1 :]:
        clean = strip_comment(raw)
        if not clean:
            continue
        if is_label_line(clean):
            break
        lda_match = re.match(r"^lda\s+#(.+)$", clean, re.IGNORECASE)
        if lda_match:
            last_lda = eval_expr(lda_match.group(1), constants, f"{path}:{lineno}")
            continue
        sta_match = re.match(r"^sta\s+(COLOR[0-4])$", clean, re.IGNORECASE)
        if sta_match and last_lda is not None:
            colors[sta_match.group(1).upper()] = last_lda & 0xFF
    fallback = {"COLOR0": 0xC8, "COLOR1": 0x24, "COLOR2": 0x0E, "COLOR3": 0x4A, "COLOR4": 0x00}
    return [colors.get(name, fallback[name]) for name in ("COLOR0", "COLOR1", "COLOR2", "COLOR3", "COLOR4")]


def le16(value: int) -> bytes:
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def build_map(font: list[int], tables: list[list[int]], colors: list[int]) -> bytes:
    tile_count = len(tables[0])
    if tile_count > EXPORT_TILE_COUNT:
        raise ParseError(f"cannot export {tile_count} logical tiles into {EXPORT_TILE_COUNT} EnvisionPC slots")

    map_data = [index if index < tile_count else 0 for index in range(MAP_W * MAP_H)]
    tile_data: list[int] = []
    for tile_id in range(EXPORT_TILE_COUNT):
        if tile_id < tile_count:
            tile_data.extend(table[tile_id] for table in tables)
        else:
            tile_data.extend((0, 0, 0, 0))

    out = bytearray()
    out.append(ANTIC_MODE)
    out.extend(le16(MAP_W))
    out.extend(le16(MAP_H))
    out.extend(colors)
    out.extend(map_data)
    out.extend(font)
    out.append(1)
    out.extend(le16(TILE_W))
    out.extend(le16(TILE_H))
    out.extend(le16(EXPORT_TILE_COUNT - 1))
    out.extend(tile_data)
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        lines = load_asm(args.source)
        constants = parse_constants(lines)
        font = parse_font(lines, constants)
        tables = [parse_table(lines, constants, name) for name in TABLE_NAMES]
        lengths = {len(table) for table in tables}
        if len(lengths) != 1:
            detail = ", ".join(f"{name}={len(table)}" for name, table in zip(TABLE_NAMES, tables))
            raise ParseError(f"tile table lengths differ: {detail}")
        colors = parse_game_palette(lines, constants)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(build_map(font, tables, colors))
        print(
            f"exported {len(font)} font bytes and {len(tables[0])} logical tiles "
            f"to {args.output} ({EXPORT_TILE_COUNT} EnvisionPC tile slots)"
        )
        return 0
    except ParseError as exc:
        print(f"export_tile_map.py: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
