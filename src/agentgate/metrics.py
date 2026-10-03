"""Bounded process-local response timings; never request contents or identities."""

import math
import time
from collections import deque
from threading import Lock

from starlette.types import ASGIApp, Message, Receive, Scope, Send

PATHS = {
    "/v1/actions/execute": "tool_action",
    "/v1/chat/completions": "model_completion",
    "/admin/playground": "operator_playground",
}


class LatencyWindow:
    def __init__(self) -> None:
        self.samples: deque[tuple[str, float]] = deque(maxlen=512)
        self.lock = Lock()

    def record(self, path: str, milliseconds: float) -> None:
        if path not in PATHS or not math.isfinite(milliseconds) or milliseconds < 0:
            return
        with self.lock:
            self.samples.append((PATHS[path], milliseconds))

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            samples = list(self.samples)
        series = {}
        for name in PATHS.values():
            values = sorted(value for route, value in samples if route == name)
            if values:
                series[name] = {
                    "count": len(values),
                    "p50_ms": round(values[math.ceil(len(values) * 0.5) - 1], 3),
                    "p95_ms": round(values[math.ceil(len(values) * 0.95) - 1], 3),
                }
        return {
            "status": "measured" if samples else "not_observed",
            "scope": "latest 512 completed POST responses in this process",
            "measurement": "request ingress through final response body; includes model/tool time",
            "excludes": "MCP, disconnected or unfinished responses; not isolated guard overhead",
            "count": len(samples),
            "series": series,
        }


class ResponseTimings:
    def __init__(self, app: ASGIApp, window: LatencyWindow) -> None:
        self.app, self.window = app, window

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or scope["method"] != "POST" or path not in PATHS:
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        recorded = False

        async def timed_send(message: Message) -> None:
            nonlocal recorded
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                if not recorded:
                    self.window.record(path, (time.monotonic() - started) * 1000)
                    recorded = True

        await self.app(scope, receive, timed_send)
