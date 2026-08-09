#!/usr/bin/env python3
"""Raw byte-streaming serial-integrity test server for the FujiNet Netstream link.

Purpose: isolate the physical serial layer (FujiNet <-> Atari POKEY) from all
game/protocol complexity. TCP is lossless and ordered, so any byte error the
Atari sees on the DOWNLINK is corruption on the POKEY receive path (external
clock, the suspect), and any byte error THIS server sees on the UPLINK is
corruption on the POKEY transmit path (internal clock). Comparing the two
directions at equal rate is the first experiment.

Wire behavior (no framing, deliberately): on connect the server streams a
rolling counter downstream (0,1,2,...,255,0,...) as fast as TCP flow control
allows -- which the FujiNet paces to the serial line rate -- and continuously
reads the uplink, verifying it is the same rolling counter. It seeds each
direction on the first byte, so any FujiNet/registration preamble only shifts
the baseline once; thereafter every discontinuity is counted as one error
event, and the XOR of expected-vs-received records which bit positions ever
flipped.

The Atari test client (atari8-client/nettest) displays the downlink error counters on
screen; this server logs the uplink counters. Run this INSTEAD of the game
server, on the same host/port the FujiNet is configured for.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time


PATTERNS = {
    "count": None,  # rolling +1
    "55": 0x55,     # 0101_0101 -- every bit transitions (stresses edges)
    "aa": 0xAA,     # 1010_1010
    "00": 0x00,     # no transitions
    "ff": 0xFF,
}


class DirectionStats:
    def __init__(self, name: str) -> None:
        self.name = name
        self.total = 0
        self.errors = 0
        self.xor_bits = 0
        self.seeded = False
        self.expected = 0

    def observe(self, data: bytes, static: int | None) -> None:
        for byte in data:
            self.total += 1
            if static is None:
                if not self.seeded:
                    self.seeded = True
                    self.expected = (byte + 1) & 0xFF
                    continue
                if byte != self.expected:
                    self.errors += 1
                    self.xor_bits |= byte ^ self.expected
                # Independent advance (do NOT resync from the received value):
                # async re-frames every byte and the ring never overflowed, so
                # errors are single-byte corruptions, not drops -- this gives an
                # exact 1:1 corruption count.
                self.expected = (self.expected + 1) & 0xFF
            else:
                if byte != static:
                    self.errors += 1
                    self.xor_bits |= byte ^ static

    def rate(self) -> float:
        return (self.errors / self.total * 100.0) if self.total else 0.0


def _reader(conn: socket.socket, up: DirectionStats, static: int | None, stop: threading.Event) -> None:
    conn.settimeout(0.5)
    while not stop.is_set():
        try:
            chunk = conn.recv(4096)
        except socket.timeout:
            continue
        except OSError:
            break
        if not chunk:
            break
        up.observe(chunk, static)
    stop.set()


def _reporter(down: DirectionStats, up: DirectionStats, start: float, stop: threading.Event,
              interval: float, log) -> None:
    while not stop.wait(interval):
        elapsed = time.monotonic() - start
        down_bps = down.total / elapsed if elapsed else 0
        up_bps = up.total / elapsed if elapsed else 0
        line = (
            f"[{elapsed:6.1f}s] "
            f"DOWN sent={down.total:>9} ({down_bps:5.0f} B/s) | "
            f"UP recv={up.total:>9} ({up_bps:5.0f} B/s) "
            f"errs={up.errors:>6} ({up.rate():.3f}%) xor=${up.xor_bits:02X}"
        )
        print(line, flush=True)
        if log:
            log.write(line + "\n")
            log.flush()


def serve_connection(conn: socket.socket, addr, static: int | None, interval: float, log) -> None:
    print(f"client connected from {addr[0]}:{addr[1]}", flush=True)
    down = DirectionStats("down")
    up = DirectionStats("up")
    stop = threading.Event()
    start = time.monotonic()
    reader = threading.Thread(target=_reader, args=(conn, up, static, stop), daemon=True)
    reporter = threading.Thread(target=_reporter, args=(down, up, start, stop, interval, log), daemon=True)
    reader.start()
    reporter.start()

    counter = 0
    block = bytearray(4096)
    try:
        conn.settimeout(1.0)
        while not stop.is_set():
            if static is None:
                for i in range(len(block)):
                    block[i] = counter
                    counter = (counter + 1) & 0xFF
                payload = bytes(block)
            else:
                payload = bytes([static]) * len(block)
            try:
                conn.sendall(payload)
            except socket.timeout:
                continue
            except OSError:
                break
            down.total += len(payload)
    finally:
        stop.set()
        elapsed = time.monotonic() - start
        print(
            f"client {addr[0]}:{addr[1]} done after {elapsed:.1f}s -- "
            f"DOWN {down.total} B, UP {up.total} B, uplink errors {up.errors} "
            f"({up.rate():.3f}%) xor=${up.xor_bits:02X}",
            flush=True,
        )
        try:
            conn.close()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9000)
    parser.add_argument("--pattern", choices=sorted(PATTERNS), default="aa",
                        help="byte pattern both directions; MUST match the client's "
                             "NET_PATTERN (default $AA). Static patterns give a "
                             "drop-immune corruption rate; 'count' detects drops but "
                             "desyncs permanently on the first drop.")
    parser.add_argument("--report", type=float, default=2.0, help="stats interval seconds")
    parser.add_argument("--log", default=None, help="append stats to this file")
    args = parser.parse_args()
    static = PATTERNS[args.pattern]
    log = open(args.log, "a") if args.log else None

    with socket.create_server((args.host, args.port), reuse_port=False) as server:
        server.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"serial test server listening on {args.host}:{args.port} "
              f"pattern={args.pattern}", flush=True)
        try:
            while True:
                conn, addr = server.accept()
                try:
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                except OSError:
                    pass
                serve_connection(conn, addr, static, args.report, log)
        except KeyboardInterrupt:
            print("\nshutting down", flush=True)
    if log:
        log.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
