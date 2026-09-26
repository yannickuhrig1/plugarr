"""Minimal read-only Sonarr-like API for the disposable Docker smoke test."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/api/v3/system/status":
            self.send_error(404)
            return
        if self.headers.get("X-Api-Key") != os.environ["PLUGARR_SMOKE_KEY"]:
            self.send_error(401)
            return
        body = json.dumps({"version": "4.0.0-smoke"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8989), Handler).serve_forever()
