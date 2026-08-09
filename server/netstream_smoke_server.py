#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import sys
import time


PROBE_BYTE = 0x42


def run(host: str, port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((host, port))
        server.listen(1)
        print(f"listening {host}:{port}", flush=True)
        conn, addr = server.accept()
        with conn:
            conn.settimeout(30)
            print(f"client {addr[0]}:{addr[1]}", flush=True)
            seen = bytearray()
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                data = conn.recv(128)
                if not data:
                    break
                seen.extend(data)
                printable = data.decode("ascii", errors="replace")
                print(f"rx {data.hex()} {printable!r}", flush=True)
                if PROBE_BYTE in data:
                    conn.sendall(bytes([PROBE_BYTE]))
                    print(f"tx {PROBE_BYTE:02x}", flush=True)
                    return 0
            print(f"probe byte {PROBE_BYTE:02x} not received; total={seen.hex()}", file=sys.stderr)
            return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)
    args = parser.parse_args()
    return run(args.host, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
