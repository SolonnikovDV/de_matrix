#!/usr/bin/env python3
"""Local TEI-compatible embedding server for DCI (sentence-transformers, port 18081)."""

from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, List


class EmbedHandler(BaseHTTPRequestHandler):
    model: Any = None
    model_id: str = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path in ("/health", "/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/embed":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return
        text = data.get("inputs", "")
        if isinstance(text, list):
            text = text[0] if text else ""
        if not isinstance(text, str):
            self.send_error(400, "inputs must be string or list of strings")
            return
        vec: List[float] = EmbedHandler.model.encode(text, normalize_embeddings=True).tolist()
        self._send_json(200, vec)


def main() -> int:
    parser = argparse.ArgumentParser(description="DCI local TEI-compatible embed server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    args = parser.parse_args()

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print(
            "ERROR: sentence-transformers not installed. Run: .venv/bin/pip install sentence-transformers",
            file=sys.stderr,
        )
        return 1

    print(f"Loading model {args.model}...", file=sys.stderr, flush=True)
    EmbedHandler.model_id = args.model
    EmbedHandler.model = SentenceTransformer(args.model)
    print(f"Embed server ready on http://{args.host}:{args.port}", file=sys.stderr, flush=True)

    server = ThreadingHTTPServer((args.host, args.port), EmbedHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down embed server", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
