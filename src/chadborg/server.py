"""Railway-style /think endpoint for the lite Borg. Stdlib only."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import chess

from .engine import choose_move
from .openings import PROFILES

# depth 3 is the macos default (~10-20 s/move on CPU); deeper is a DoS lever on a public box.
MAX_DEPTH = 3
MAX_BODY = 64 * 1024


def parse_think_request(data: object) -> tuple[str, str, int | None]:
    """Validate a /think JSON body. Raises ValueError with a client-facing message."""
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    fen = data.get("fen")
    if fen is None or fen == "":
        fen = chess.STARTING_FEN
    elif not isinstance(fen, str):
        raise ValueError("fen must be a string")
    profile = data.get("profile")
    if profile is None or profile == "":
        profile = "lite"
    elif not isinstance(profile, str) or profile.lower() not in PROFILES:
        raise ValueError(f"profile must be one of {list(PROFILES)}")
    profile = profile.lower()
    depth = data.get("depth")
    if depth is not None:
        if isinstance(depth, bool) or not isinstance(depth, int):
            raise ValueError("depth must be an integer")
        if not 1 <= depth <= MAX_DEPTH:
            raise ValueError(f"depth must be between 1 and {MAX_DEPTH}")
    return fen, profile, depth


def think_payload(fen: str, profile: str = "lite", depth: int | None = None) -> dict:
    board = chess.Board(fen) if fen else chess.Board()
    if not board.is_valid():
        raise ValueError("illegal position")
    thought = choose_move(board, profile=profile, depth=depth)
    return {
        "fen": board.fen(),
        "profile": profile,
        "choice": thought.choice.uci(),
        "choice_san": board.san(thought.choice),
        "assists": thought.assists,
        "top": [
            {
                "uci": r.uci,
                "san": r.san,
                "score": round(r.score, 2),
                "gives_mate": r.gives_mate,
                "walks_into_mate": r.walks_into_mate,
            }
            for r in thought.ranked[:8]
        ],
    }


class ThinkHandler(BaseHTTPRequestHandler):
    server_version = "chadborg-lite/0.4"

    def log_message(self, fmt: str, *args) -> None:
        print("[think]", self.address_string(), fmt % args)

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/info"):
            self._send(
                200,
                {
                    "name": "Coach Chad Borg lite",
                    "loop": "1-ply legal rank + book",
                    "black_first": "always 1...g5 when legal",
                    "think": "POST /think {fen, profile, depth}",
                },
            )
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/think":
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._send(400, {"error": "bad content-length"})
            return
        if n < 0 or n > MAX_BODY:
            self._send(413, {"error": "body too large"})
            return
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._send(400, {"error": "bad json"})
            return
        try:
            fen, profile, depth = parse_think_request(data)
            payload = think_payload(fen, profile=profile, depth=depth)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        except Exception as exc:  # never drop the socket without a response
            self.log_message("think failed: %r", exc)
            self._send(500, {"error": "internal error"})
            return
        self._send(200, payload)

def serve(host: str = "0.0.0.0", port: int = 8787) -> None:
    httpd = ThreadingHTTPServer((host, port), ThinkHandler)
    print(f"chadborg lite /think on http://{host}:{port}/think")
    httpd.serve_forever()
