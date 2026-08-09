from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Callable
from urllib import error, request


@dataclass(frozen=True)
class LobbyConfig:
    base_url: str
    game: str
    creator_id: int
    app_id: int
    server: str
    region: str
    server_url: str
    max_players: int
    client_platform: str
    client_url: str
    timeout: float = 2.0

    @property
    def appkey(self) -> int:
        return self.app_id & 0xFF

    def payload(self, curplayers: int, status: str) -> dict[str, object]:
        return {
            "game": self.game,
            "appkey": self.appkey,
            "server": self.server,
            "region": self.region,
            "serverurl": self.server_url,
            "status": status,
            "maxplayers": self.max_players,
            "curplayers": curplayers,
            "clients": [
                {
                    "platform": self.client_platform,
                    "url": self.client_url,
                }
            ],
        }


class LobbyPublisher:
    def __init__(self, config: LobbyConfig, log_error: Callable[[str], None]) -> None:
        self.config = config
        self.log_error = log_error

    def _request_json(self, method: str, path: str, payload: dict[str, object] | None = None) -> bool:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.config.base_url.rstrip('/')}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=self.config.timeout) as response:
                response.read()
            return True
        except error.HTTPError as exc:
            detail = ""
            try:
                body = exc.read().decode("utf-8", errors="replace").strip()
            except OSError:
                body = ""
            if body:
                detail = f" body={body}"
            self.log_error(f"lobby {method} {path} failed: {exc}{detail}")
            return False
        except (error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
            self.log_error(f"lobby {method} {path} failed: {exc}")
            return False

    def probe_version(self) -> bool:
        req = request.Request(f"{self.config.base_url.rstrip('/')}/version", method="GET")
        try:
            with request.urlopen(req, timeout=self.config.timeout) as response:
                response.read()
            return True
        except error.HTTPError as exc:
            detail = ""
            try:
                body = exc.read().decode("utf-8", errors="replace").strip()
            except OSError:
                body = ""
            if body:
                detail = f" body={body}"
            self.log_error(f"lobby GET /version failed: {exc}{detail}")
            return False
        except (error.URLError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
            self.log_error(f"lobby GET /version failed: {exc}")
            return False

    def publish(self, curplayers: int, status: str) -> bool:
        return self._request_json("POST", "/server", self.config.payload(curplayers, status))

    def delete(self) -> bool:
        return self._request_json("DELETE", "/server", {"serverurl": self.config.server_url})
