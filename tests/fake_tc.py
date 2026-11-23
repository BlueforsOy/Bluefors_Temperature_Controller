"""In-process fake Temperature Controller for tests.

It mimics the replies of a real controller (software 2.x, API version 2):
HTTP request-response on one port, the measurement stream on a WebSocket
port, ``{"status": "ERROR", "error_msg": ...}`` with HTTP 400 for rejected
requests, and an HTML 404 page for unknown endpoints.
"""

from __future__ import annotations

import asyncio
import copy
import json
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional

from websockets.asyncio.server import serve


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_time(text: str) -> float:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            pass
    raise ValueError(text)


class FakeTC:
    def __init__(self) -> None:
        self.system = {
            "api_version": 2,
            "type": "Bluefors TC",
            "serial": "9999",
            "label": "fake",
            "software_version": "tc-tc11_2.0.1+fake",
        }
        self.channels = {
            nr: {
                "channel_nr": nr,
                "active": nr <= 3,
                "name": f"Channel {nr}",
                "coupled_heater_nr": 0,
                "calib_curve_nr": 1 if nr <= 2 else 100,
            }
            for nr in range(1, 13)
        }
        self.heaters = {
            nr: {
                "heater_nr": nr,
                "active": False,
                "name": f"Heater {nr}",
                "pid_mode": 0,
                "resistance": 120,
                "power": 0.0,
                "max_power": 0.001,
                "setpoint": 0.01,
                "target_temperature": 0.01,
                "control_algorithm": 1,
                "control_algorithm_settings": {
                    "proportional": 0.01,
                    "integral": 100,
                    "derivative": 0,
                },
                "relay_mode": 1,
                "relay_status": 1,
            }
            for nr in range(1, 5)
        }
        now = time.time()
        self.history = {
            1: [(now - 300, 0.0101, 1500.0), (now - 30, 0.0102, 1490.0)],
            2: [(now - 200, 4.2, 120.0)],
        }
        self.requests: list[tuple[str, str, Optional[dict[str, Any]]]] = []
        self.stream_period = 0.02
        self.listen_open = 0
        self.http_port = 0
        self.ws_port = 0
        self._http: Optional[ThreadingHTTPServer] = None

    # ------------------------------------------------------------------ helpers

    def measurement(self, nr: int) -> dict[str, Any]:
        calibrated = self.channels[nr]["calib_curve_nr"] != 100
        return {
            "channel_nr": nr,
            "temperature": 0.01 * nr if calibrated else None,
            "resistance": 1000.0 + nr,
            "reactance": -1.0,
            "timestamp": time.time(),
            "settings_nr": nr,
            "status_flags": [] if calibrated else [519],
        }

    def handle(self, method: str, path: str, body: Optional[dict[str, Any]]) -> tuple[int, Any]:
        self.requests.append((method, path, body))
        ok = {"datetime": _now(), "status": "OK"}

        def error(message: Any) -> tuple[int, Any]:
            return 400, {"status": "ERROR", "error_msg": message}

        if method == "GET":
            if path == "system":
                return 200, {**self.system, **ok}
            if path == "statemachine":
                return 200, {"state": "measuring", "measuring": True, "channel_nr": 1, **ok}
            if path == "channels":
                return 200, {"data": list(self.channels.values()), **ok}
            if path == "heaters":
                return 200, {"data": list(self.heaters.values()), **ok}
            if path == "channel/measurement/latest":
                return 200, {**self.measurement(3), **ok}
            return 404, None

        if body is None:
            return error(400)
        if path == "channel":
            return 200, {**self.channels[body["channel_nr"]], **ok}
        if path == "channel/update":
            self.channels[body["channel_nr"]].update(body)
            return 200, {**self.channels[body["channel_nr"]], **ok}
        if path == "channel/heater/update":
            for c in self.channels.values():
                if c["coupled_heater_nr"] == body["heater_nr"] and body["heater_nr"]:
                    c["coupled_heater_nr"] = 0
            self.channels[body["channel_nr"]]["coupled_heater_nr"] = body["heater_nr"]
            return 200, {"relations": [], **ok}
        if path in ("heater", "heater/update"):
            nr = body.get("heater_nr")
            if not isinstance(nr, int) or not 1 <= nr <= 4:
                return error(
                    f"Incoming request validation failed: {nr} is greater than the maximum of 4"
                )
            if path == "heater/update":
                for key, value in body.items():
                    if key == "control_algorithm_settings":
                        self.heaters[nr][key].update(value)
                    else:
                        self.heaters[nr][key] = value
            return 200, {**copy.deepcopy(self.heaters[nr]), **ok}
        if path in ("channel/historical-data", "heater/historical-data"):
            for key in ("start_time", "stop_time"):
                if not isinstance(body.get(key), str):
                    reason = f"{body.get(key)} is not of type 'string'"
                    return error(f"Incoming request validation failed: {reason}")
            start, stop = _parse_time(body["start_time"]), _parse_time(body["stop_time"])
            if path.startswith("heater"):
                rows = [(time.time() - 60, 0.0005, 0.002)]
                names = ("timestamp", "power", "current")
            else:
                rows = self.history.get(body["channel_nr"], [])
                names = ("timestamp", "temperature", "resistance")
            rows = [r for r in rows if start <= r[0] <= stop]
            fields = [f for f in body["fields"] if f in names]
            measurements = {f: [r[names.index(f)] for r in rows] for f in fields}
            return 200, {
                **body,
                "fields": fields,
                "measurements": measurements,
                "over_limit": False,
                **ok,
            }
        return 404, None

    # ------------------------------------------------------------------ servers

    def start(self) -> FakeTC:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _reply(self, method: str) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b""
                body = json.loads(raw) if raw else None
                status, data = fake.handle(method, self.path.strip("/"), body)
                if data is None:
                    payload = b"<html><title>404: Wrong endpoint</title></html>"
                    content_type = "text/html"
                else:
                    payload = json.dumps(data).encode()
                    content_type = "application/json"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:  # noqa: N802
                self._reply("GET")

            def do_POST(self) -> None:  # noqa: N802
                self._reply("POST")

        self._http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.http_port = self._http.server_address[1]
        threading.Thread(target=self._http.serve_forever, daemon=True).start()

        ready = threading.Event()

        async def listen(ws: Any) -> None:
            if ws.request.path != "/channel/measurement/listen":
                await ws.close()
                return
            self.listen_open += 1
            try:
                i = 0
                while True:
                    active = [nr for nr, c in self.channels.items() if c["active"]]
                    if active:
                        await ws.send(json.dumps(self.measurement(active[i % len(active)])))
                        i += 1
                    await asyncio.sleep(self.stream_period)
            except Exception:
                pass
            finally:
                self.listen_open -= 1

        async def main() -> None:
            async with serve(listen, "127.0.0.1", 0) as server:
                self.ws_port = server.sockets[0].getsockname()[1]
                ready.set()
                await asyncio.Future()

        threading.Thread(target=lambda: asyncio.run(main()), daemon=True).start()
        ready.wait(5)
        return self

    def stop(self) -> None:
        if self._http:
            self._http.shutdown()
