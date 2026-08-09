"""Phase 7.6 login/resume TCP server.

serve() runs a persistent, nonblocking selector loop handling many
connections concurrently, each limited to one request/response within an
absolute deadline. Hostile or broken peers (port scanners that reset
mid-request, bots that trickle bytes to hold a connection open) cost only
their own connection; they can neither block other clients nor crash the
process.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import selectors
import socket
import time
from typing import Any

try:
    from .protocol import (
        LOGIN_OK,
        LOGIN_USERNAME_TAKEN,
        RENAME_OK,
        RENAME_TOKEN_UNKNOWN,
        RENAME_USERNAME_TAKEN,
        RESUME_OK,
        LoginResponse,
        PacketError,
        PacketStreamDecoder,
        PacketType,
        RenameResponse,
        ResumeResponse,
        decode_login_request,
        decode_rename_request,
        decode_resume_request,
        encode_login_response,
        encode_rename_response,
        encode_resume_response,
    )
except ImportError:  # pragma: no cover - direct script execution
    from protocol import (
        LOGIN_OK,
        LOGIN_USERNAME_TAKEN,
        RENAME_OK,
        RENAME_TOKEN_UNKNOWN,
        RENAME_USERNAME_TAKEN,
        RESUME_OK,
        LoginResponse,
        PacketError,
        PacketStreamDecoder,
        PacketType,
        RenameResponse,
        ResumeResponse,
        decode_login_request,
        decode_rename_request,
        decode_resume_request,
        encode_login_response,
        encode_rename_response,
        encode_resume_response,
    )


LOGIN_PORT = 9010
DEFAULT_STORE = Path(__file__).with_name("sessions.json")
DEFAULT_CLIENT_TIMEOUT = 5.0
# Concurrent-connection cap: deadlines recycle slots within client_timeout,
# so even a flood keeps a slot opening for real clients every few seconds.
LOGIN_MAX_CLIENTS = 64
# A connection that has sent this much without completing a request is
# feeding garbage; drop it rather than scan it until the deadline.
LOGIN_MAX_REQUEST_BYTES = 4096


def generate_token() -> str:
    return str(random.getrandbits(32))


class SessionStore:
    def __init__(self, path: str | Path = DEFAULT_STORE) -> None:
        self.path = Path(path)
        self.sessions: dict[str, dict[str, Any]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            self.sessions = {}
            return
        raw = json.loads(self.path.read_text(encoding="ascii"))
        sessions: dict[str, dict[str, Any]] = {}
        for token, record in raw.get("sessions", {}).items():
            token_text = str(token)
            if isinstance(record, dict):
                normalized = dict(record)
                normalized["username"] = str(record.get("username", ""))
                if not isinstance(normalized.get("player_state"), dict):
                    normalized.pop("player_state", None)
                sessions[token_text] = normalized
                continue
            sessions[token_text] = {"username": str(record)}
        self.sessions = sessions

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"sessions": self.sessions}
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
        tmp_path.replace(self.path)

    def get_record(self, token: str | int) -> dict[str, Any] | None:
        token_text = str(token)
        if self.path.exists():
            self.load()
        return self.sessions.get(token_text)

    def load_player_state(self, token: str | int) -> dict[str, Any] | None:
        record = self.get_record(token)
        if record is None:
            return None
        state = record.get("player_state")
        if not isinstance(state, dict):
            return None
        return dict(state)

    def save_player_state(self, token: str | int, username: str, player_state: dict[str, Any]) -> None:
        if self.path.exists():
            self.load()
        token_text = str(token)
        record = dict(self.sessions.get(token_text, {}))
        record["username"] = str(record.get("username") or username)
        record["player_state"] = dict(player_state)
        self.sessions[token_text] = record
        self.save()

    def set_online(self, token: str | int, online: bool) -> None:
        if self.path.exists():
            self.load()
        token_text = str(token)
        record = dict(self.sessions.get(token_text, {}))
        try:
            fallback_username = f"Player{int(token_text) & 0xFFFF:04X}"
        except ValueError:
            fallback_username = f"Player{token_text[-4:]}"
        record["username"] = str(record.get("username", fallback_username))
        record["online"] = bool(online)
        record["last_seen_at"] = int(time.time())
        self.sessions[token_text] = record
        self.save()

    def set_all_offline(self) -> None:
        if self.path.exists():
            self.load()
        changed = False
        now = int(time.time())
        for token_text, record in list(self.sessions.items()):
            normalized = dict(record)
            if normalized.get("online"):
                normalized["online"] = False
                normalized["last_seen_at"] = now
                self.sessions[token_text] = normalized
                changed = True
        if changed:
            self.save()

    def username_taken(self, username: str, except_token: str | None = None) -> bool:
        return any(
            token != except_token and record["username"] == username for token, record in self.sessions.items()
        )

    def register(self, username: str) -> str | None:
        if self.path.exists():
            self.load()
        if self.username_taken(username):
            return None
        token = generate_token()
        while token in self.sessions:
            token = generate_token()
        self.sessions[token] = {"username": username}
        self.save()
        return token

    def resume(self, token: str) -> str:
        if self.path.exists():
            self.load()
        record = self.sessions.get(token)
        if record is not None:
            return record["username"]
        username = f"Player{token[-4:]}" if token else "Player"
        self.sessions[token] = {"username": username}
        self.save()
        return username

    def rename(self, token: str, username: str) -> int:
        if self.path.exists():
            self.load()
        record = self.sessions.get(token)
        if record is None:
            return RENAME_TOKEN_UNKNOWN
        if self.username_taken(username, except_token=token):
            return RENAME_USERNAME_TAKEN
        renamed = dict(record)
        renamed["username"] = username
        self.sessions[token] = renamed
        self.save()
        return RENAME_OK


class _PendingClient:
    __slots__ = ("addr", "deadline", "decoder", "response", "sent", "rx_bytes")

    def __init__(self, addr: tuple[str, int], deadline: float) -> None:
        self.addr = addr
        self.deadline = deadline
        self.decoder = PacketStreamDecoder()
        self.response: bytes | None = None
        self.sent = 0
        self.rx_bytes = 0


class LoginServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = LOGIN_PORT,
        store: SessionStore | None = None,
        client_timeout: float = DEFAULT_CLIENT_TIMEOUT,
        debug: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.store = store if store is not None else SessionStore()
        self.client_timeout = client_timeout
        self.debug = debug

    def _log(self, message: str) -> None:
        if self.debug:
            print(message)

    def _response_for(self, packet) -> bytes | None:
        if packet.packet_type == PacketType.LOGIN_REQUEST:
            request = decode_login_request(packet.payload)
            token = self.store.register(request.username)
            if token is None:
                self._log(f"login rejected username={request.username}")
                return encode_login_response(LoginResponse(LOGIN_USERNAME_TAKEN, "0"))
            self._log(f"login ok username={request.username} token={token}")
            return encode_login_response(LoginResponse(LOGIN_OK, token))
        if packet.packet_type == PacketType.RESUME_REQUEST:
            request = decode_resume_request(packet.payload)
            username = self.store.resume(request.token)
            self._log(f"resume ok username={username} token={request.token}")
            return encode_resume_response(ResumeResponse(RESUME_OK, username))
        if packet.packet_type == PacketType.RENAME_REQUEST:
            request = decode_rename_request(packet.payload)
            status = self.store.rename(request.token, request.username)
            self._log(f"rename status={status} token={request.token}")
            return encode_rename_response(RenameResponse(status))
        return None

    # ------------------------------------------------------------------
    # Concurrent selector loop (production path)

    def serve(self, duration: float | None = None) -> None:
        stop_at = None if duration is None else time.monotonic() + duration
        selector = selectors.DefaultSelector()
        clients: dict[socket.socket, _PendingClient] = {}
        with socket.create_server((self.host, self.port), reuse_port=False) as server:
            server.setblocking(False)
            selector.register(server, selectors.EVENT_READ)
            self._log(f"login listening {self.host}:{self.port}")
            try:
                while stop_at is None or time.monotonic() < stop_at:
                    for key, mask in selector.select(0.2):
                        if key.fileobj is server:
                            self._accept_clients(server, selector, clients)
                            continue
                        conn = key.fileobj
                        assert isinstance(conn, socket.socket)
                        client = clients.get(conn)
                        if client is None:
                            continue
                        if mask & selectors.EVENT_WRITE:
                            self._flush_client(selector, clients, conn, client)
                        if conn in clients and mask & selectors.EVENT_READ:
                            self._read_client(selector, clients, conn, client)
                    now = time.monotonic()
                    for conn, client in list(clients.items()):
                        if now >= client.deadline:
                            self._drop_client(selector, clients, conn, "request deadline")
            finally:
                for conn in list(clients):
                    self._drop_client(selector, clients, conn, "server stopping")
                selector.close()

    def _accept_clients(
        self,
        server: socket.socket,
        selector: selectors.BaseSelector,
        clients: dict[socket.socket, _PendingClient],
    ) -> None:
        while True:
            try:
                conn, addr = server.accept()
            except BlockingIOError:
                return
            except OSError as exc:
                # ECONNABORTED, EMFILE, ...: shed and keep listening.
                self._log(f"login accept failed: {exc}")
                return
            if len(clients) >= LOGIN_MAX_CLIENTS:
                try:
                    conn.close()
                except OSError:
                    pass
                self._log(f"login shed client {addr[0]}:{addr[1]} (table full)")
                continue
            conn.setblocking(False)
            clients[conn] = _PendingClient(addr, time.monotonic() + self.client_timeout)
            selector.register(conn, selectors.EVENT_READ)
            self._log(f"login client {addr[0]}:{addr[1]}")

    def _read_client(
        self,
        selector: selectors.BaseSelector,
        clients: dict[socket.socket, _PendingClient],
        conn: socket.socket,
        client: _PendingClient,
    ) -> None:
        try:
            chunk = conn.recv(1024)
        except BlockingIOError:
            return
        except OSError as exc:
            self._drop_client(selector, clients, conn, f"recv failed: {exc}")
            return
        if not chunk:
            self._drop_client(selector, clients, conn, "closed by peer")
            return
        if client.response is not None:
            return
        client.rx_bytes += len(chunk)
        if client.rx_bytes > LOGIN_MAX_REQUEST_BYTES:
            self._drop_client(selector, clients, conn, "request flood")
            return
        for packet in client.decoder.feed(chunk):
            try:
                response = self._response_for(packet)
            except PacketError as exc:
                self._drop_client(selector, clients, conn, f"bad packet: {exc}")
                return
            except Exception as exc:  # session-store failure: contain it
                self._drop_client(selector, clients, conn, f"internal error: {exc!r}")
                return
            if response is None:
                continue
            client.response = response
            self._flush_client(selector, clients, conn, client)
            return

    def _flush_client(
        self,
        selector: selectors.BaseSelector,
        clients: dict[socket.socket, _PendingClient],
        conn: socket.socket,
        client: _PendingClient,
    ) -> None:
        if client.response is None:
            return
        try:
            sent = conn.send(client.response[client.sent :])
        except BlockingIOError:
            sent = 0
        except OSError as exc:
            self._drop_client(selector, clients, conn, f"send failed: {exc}")
            return
        client.sent += sent
        if client.sent >= len(client.response):
            self._drop_client(selector, clients, conn, "served")
            return
        try:
            selector.modify(conn, selectors.EVENT_WRITE)
        except (KeyError, ValueError):
            pass

    def _drop_client(
        self,
        selector: selectors.BaseSelector,
        clients: dict[socket.socket, _PendingClient],
        conn: socket.socket,
        reason: str,
    ) -> None:
        client = clients.pop(conn, None)
        peer = f"{client.addr[0]}:{client.addr[1]}" if client is not None else "?"
        self._log(f"login client {peer} closed ({reason})")
        try:
            selector.unregister(conn)
        except (KeyError, ValueError):
            pass
        try:
            conn.close()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Blocking single-connection path (tests and --once)

    def serve_once(self) -> None:
        with socket.create_server((self.host, self.port), reuse_port=False) as server:
            server.listen(1)
            self._log(f"login listening {self.host}:{self.port}")
            try:
                conn, addr = server.accept()
            except OSError as exc:
                self._log(f"login accept failed: {exc}")
                return
            with conn:
                self._log(f"login client {addr[0]}:{addr[1]}")
                try:
                    self.handle_client(conn)
                finally:
                    self._log(f"login client {addr[0]}:{addr[1]} closed")

    def handle_client(self, conn: socket.socket) -> None:
        decoder = PacketStreamDecoder()
        # Absolute deadline, re-armed before every recv: a peer trickling
        # bytes cannot hold the connection past client_timeout.
        deadline = time.monotonic() + self.client_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._log("login dropped client: request deadline")
                return
            try:
                conn.settimeout(remaining)
                chunk = conn.recv(1024)
            except socket.timeout:
                self._log("login dropped idle client: recv timeout")
                return
            except OSError as exc:
                self._log(f"login client recv failed: {exc}")
                return
            if not chunk:
                self._log("login client closed by peer")
                return
            for packet in decoder.feed(chunk):
                try:
                    response = self._response_for(packet)
                except PacketError as exc:
                    self._log(f"login dropped bad packet: {exc}")
                    return
                except Exception as exc:  # session-store failure: contain it
                    self._log(f"login request failed: {exc!r}")
                    return
                if response is None:
                    continue
                try:
                    conn.sendall(response)
                except OSError as exc:
                    self._log(f"login response send failed: {exc}")
                return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=LOGIN_PORT)
    parser.add_argument("--store", default=str(DEFAULT_STORE))
    parser.add_argument("--client-timeout", type=float, default=DEFAULT_CLIENT_TIMEOUT)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    server = LoginServer(
        args.host,
        args.port,
        SessionStore(args.store),
        client_timeout=args.client_timeout,
        debug=args.debug,
    )
    if args.once:
        server.serve_once()
        return 0
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
