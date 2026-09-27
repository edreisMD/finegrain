"""Finegrain training coordinator UI. The company brain/UI/auth are Gbrain's."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

from .config import Config
from .models import canonical
from .runtime import read_status, run_worker


def make_http_server(config: Config, host="127.0.0.1", port=8787):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            if self.path == "/healthz":
                body, kind = b'{"status":"ok"}', "application/json"
            elif self.path == "/api/status":
                raw = read_status(config)
                # Only operational counters are exposed. No questions, pages, tokens or paths.
                value = {k: raw[k] for k in ("state", "updated_at", "error", "message") if k in raw}
                value.update(
                    company=config.tenant,
                    cadence=config.cadence,
                    auto_train=config.auto_train,
                    gbrain_url=config.server_url,
                    teacher=config.teacher_model,
                    student=config.student_model,
                    foundation=config.foundation_name if config.foundation_checkpoint else None,
                )
                latest = raw.get("latest_dataset")
                if latest:
                    from pathlib import Path

                    manifest = Path(latest) / "manifest.json"
                    if manifest.exists():
                        data = json.loads(manifest.read_text())
                        value.update(
                            counts=data["counts"], pages=data["memories"], demo=data["demo"]
                        )
                body, kind = canonical(value).encode(), "application/json"
            elif self.path == "/":
                body = files("finegrain").joinpath("web/index.html").read_bytes()
                kind = "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

    return ThreadingHTTPServer((host, port), Handler)


def serve(config: Config, host="127.0.0.1", port=8787, worker=True):
    if config.role != "server":
        raise ValueError("Use a company server profile")
    if worker:
        threading.Thread(target=run_worker, args=(config,), daemon=True).start()
    server = make_http_server(config, host, port)
    try:
        print(f"Finegrain training console: http://{host}:{port}", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
