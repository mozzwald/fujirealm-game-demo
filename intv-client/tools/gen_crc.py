#!/usr/bin/env python3
"""Generate crc_tab.bas: CRC-16/CCITT-FALSE split hi/lo tables for IntyBASIC.

The realtime v3 protocol frames carry CRC-16/CCITT-FALSE (poly 0x1021, init
0xFFFF, MSB-first, no reflection, no final XOR) over header+payload. On the
CP-1610 the table-driven form is the only affordable one; IntyBASIC DATA
tables are indexable like read-only arrays, so we emit two 256-entry tables
and the per-byte update becomes:

    cx     = crc_h XOR byte
    crc_h  = crc_l XOR crc_hi_tab(cx)
    crc_l  = crc_lo_tab(cx)

which mirrors lynx-client/src/rt_state.c's dual-table implementation.

Usage: python3 tools/gen_crc.py > crc_tab.bas   (run from intv-client/)
"""

POLY = 0x1021


def crc_table():
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        table.append(crc)
    return table


def crc16(data, table):
    crc = 0xFFFF
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ table[((crc >> 8) ^ b) & 0xFF]
    return crc


def main():
    table = crc_table()
    check = crc16(b"123456789", table)
    assert check == 0x29B1, f"CRC self-test failed: got {check:#06x}, want 0x29b1"

    print("' crc_tab.bas -- CRC-16/CCITT-FALSE lookup tables (GENERATED FILE)")
    print("' Regenerate with: python3 tools/gen_crc.py > crc_tab.bas")
    print("' Self-test: CRC(\"123456789\") = $29B1 (verified at generation time).")
    print("'")
    print("' Per-byte update (see rt.bas):")
    print("'   cx = crc_h XOR byte : crc_h = crc_l XOR crc_hi_tab(cx) : crc_l = crc_lo_tab(cx)")
    for name, shift in (("crc_hi_tab", 8), ("crc_lo_tab", 0)):
        print(f"{name}:")
        for row in range(0, 256, 16):
            vals = ",".join(f"${(table[i] >> shift) & 0xFF:02X}" for i in range(row, row + 16))
            print(f"    DATA {vals}")
    print()


if __name__ == "__main__":
    main()
