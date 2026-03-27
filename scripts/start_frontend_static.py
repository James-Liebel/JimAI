"""Serve the built frontend bundle with SPA route fallback."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "frontend" / "dist"


class JimAIStaticHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        if self.path.endswith(".html") or self.path == "/" or "/assets/" not in self.path:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        self._serve()

    def do_HEAD(self) -> None:
        self._serve(head_only=True)

    def _serve(self, *, head_only: bool = False) -> None:
        parsed = urlparse(self.path)
        request_path = unquote(parsed.path or "/")
        if request_path.startswith("/api/") or request_path == "/health":
            self.send_error(502, "Frontend static server does not proxy API routes.")
            return

        full_path = Path(self.directory or DIST_DIR) / request_path.lstrip("/")
        has_extension = bool(Path(request_path).suffix)
        if request_path == "/" or (not has_extension and not full_path.exists()):
            self.path = "/index.html"
        else:
            self.path = request_path

        if head_only:
            super().do_HEAD()
            return
        super().do_GET()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve jimAI static frontend bundle.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5173)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if not DIST_DIR.exists():
        raise SystemExit(f"Frontend build output not found: {DIST_DIR}")

    handler = partial(JimAIStaticHandler, directory=str(DIST_DIR))
    httpd = ThreadingHTTPServer((args.host, int(args.port)), handler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
