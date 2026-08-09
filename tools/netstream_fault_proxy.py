#!/usr/bin/env python3
"""Deterministic TCP fault proxy for the realtime v3 (COBS/CRC-16) stream.

The proxy is intentionally small and dependency-free. It accepts one FujiNet
connection, forwards both directions, and can deterministically delete bytes,
or delete/corrupt/duplicate whole zero-delimited v3 wire frames, in either
direction. It reproduces serial-loss recovery scenarios without an emulator
or real Atari hardware.

Byte faults operate below the framing (they exercise COBS/CRC recovery);
frame faults operate on complete delimiter-bounded frames (they exercise the
retransmit/commit/timeout state machines). The seed makes corrupt-byte
positions reproducible across runs.

Examples:
  # Drop every 40th downstream (server->client) frame:
  netstream_fault_proxy.py --listen-port 9100 --server-port 9000 \\
      --drop-frame-every 40 --direction downstream

  # Delete every 500th raw byte in both directions:
  netstream_fault_proxy.py --listen-port 9100 --server-port 9000 \\
      --drop-byte-every 500 --direction both
"""

from __future__ import annotations

import argparse
import random
import selectors
import socket
from dataclasses import dataclass, field


@dataclass
class FaultPlan:
    name: str = "downstream"
    drop_byte_every: int = 0
    drop_frame_every: int = 0
    corrupt_frame_every: int = 0
    duplicate_frame_every: int = 0
    rng: random.Random = field(default_factory=random.Random)
    byte_count: int = 0
    frame_count: int = 0
    frames_dropped: int = 0
    frames_corrupted: int = 0
    frames_duplicated: int = 0
    bytes_dropped: int = 0
    buffer: bytearray = field(default_factory=bytearray)

    def frame_faults_active(self) -> bool:
        return bool(self.drop_frame_every or self.corrupt_frame_every or self.duplicate_frame_every)

    def feed(self, data: bytes) -> bytes:
        data = self._byte_faults(data)
        if not self.frame_faults_active():
            return data
        # Frame faults need delimiter-bounded framing: hold bytes until the
        # next zero terminates the current frame. The RT3 preamble and any
        # pre-frame noise pass through with the first complete frame.
        self.buffer.extend(data)
        output = bytearray()
        while True:
            delim = self.buffer.find(b"\x00")
            if delim < 0:
                break
            frame = bytes(self.buffer[: delim + 1])
            del self.buffer[: delim + 1]
            if len(frame) == 1:
                output += frame  # bare delimiter, keep alignment
                continue
            self.frame_count += 1
            if self.drop_frame_every and self.frame_count % self.drop_frame_every == 0:
                self.frames_dropped += 1
                continue
            if self.corrupt_frame_every and self.frame_count % self.corrupt_frame_every == 0:
                damaged = bytearray(frame)
                index = self.rng.randrange(0, len(damaged) - 1)
                damaged[index] ^= 1 << self.rng.randrange(8)
                if damaged[index] == 0:
                    damaged[index] = 0xFF
                frame = bytes(damaged)
                self.frames_corrupted += 1
            output += frame
            if self.duplicate_frame_every and self.frame_count % self.duplicate_frame_every == 0:
                output += frame
                self.frames_duplicated += 1
        return bytes(output)

    def _byte_faults(self, data: bytes) -> bytes:
        if self.drop_byte_every <= 0:
            return data
        output = bytearray()
        for value in data:
            self.byte_count += 1
            if self.byte_count % self.drop_byte_every == 0:
                self.bytes_dropped += 1
                continue
            output.append(value)
        return bytes(output)

    def summary(self) -> str:
        return (
            f"{self.name}: frames={self.frame_count} dropped={self.frames_dropped} "
            f"corrupted={self.frames_corrupted} duplicated={self.frames_duplicated} "
            f"bytes_dropped={self.bytes_dropped}"
        )


def run(args: argparse.Namespace) -> None:
    downstream = FaultPlan(name="downstream", rng=random.Random(args.seed))
    upstream = FaultPlan(name="upstream", rng=random.Random(args.seed + 1))
    for plan in (downstream, upstream):
        if args.direction in ("both", plan.name):
            plan.drop_byte_every = args.drop_byte_every
            plan.drop_frame_every = args.drop_frame_every
            plan.corrupt_frame_every = args.corrupt_frame_every
            plan.duplicate_frame_every = args.duplicate_frame_every

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((args.listen_host, args.listen_port))
    listener.listen(1)
    print(f"fault proxy listening on {args.listen_host}:{args.listen_port}", flush=True)
    client, address = listener.accept()
    print(f"client connected from {address[0]}:{address[1]}", flush=True)
    server = socket.create_connection((args.server_host, args.server_port))
    client.setblocking(False)
    server.setblocking(False)
    selector = selectors.DefaultSelector()
    selector.register(client, selectors.EVENT_READ, (server, upstream))
    selector.register(server, selectors.EVENT_READ, (client, downstream))
    try:
        while True:
            for key, _ in selector.select():
                source = key.fileobj
                assert isinstance(source, socket.socket)
                target, plan = key.data
                try:
                    data = source.recv(4096)
                except OSError:
                    return
                if not data:
                    return
                transformed = plan.feed(data)
                if transformed:
                    target.sendall(transformed)
    finally:
        print(downstream.summary(), flush=True)
        print(upstream.summary(), flush=True)
        selector.close()
        client.close()
        server.close()
        listener.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, required=True)
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--server-port", type=int, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--drop-byte-every", type=int, default=0)
    parser.add_argument("--drop-frame-every", type=int, default=0)
    parser.add_argument("--corrupt-frame-every", type=int, default=0)
    parser.add_argument("--duplicate-frame-every", type=int, default=0)
    parser.add_argument(
        "--direction", choices=("downstream", "upstream", "both"), default="downstream"
    )
    args = parser.parse_args()
    for value in (
        args.drop_byte_every,
        args.drop_frame_every,
        args.corrupt_frame_every,
        args.duplicate_frame_every,
    ):
        if value < 0:
            parser.error("fault intervals must be non-negative")
    try:
        run(args)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
