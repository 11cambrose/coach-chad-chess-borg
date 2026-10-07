"""Regression tests for bugs found in QA of the 0.4.0 upload (2026-10-06)."""

import json
import random
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import chess
import pytest

from chadborg.engine import choose_move
from chadborg.eval import evaluate_for
from chadborg.search import MATE, _quiesce
from chadborg.server import MAX_DEPTH, ThinkHandler, parse_think_request

# --- Bug 1: quiescence always maximized for the root side -----------------------

KNIGHT_GRAB = "r1bqkbnr/pppp1ppp/2n5/4N3/4P3/8/PPPP1PPP/RNBQKB1R b KQkq - 0 3"  # 1.e4 e5 2.Nf3 Nc6 3.Nxe5


def test_quiesce_lets_opponent_recapture():
    board = chess.Board(KNIGHT_GRAB)
    after = board.copy()
    after.push_san("Nxe5")
    value = _quiesce(board, chess.WHITE, -MATE, MATE, 2)
    # Black to move will recapture; White's value can be no better than after ...Nxe5.
    assert value <= evaluate_for(after, chess.WHITE)


@pytest.mark.parametrize(
    "fen",
    [
        KNIGHT_GRAB,
        "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
        "r2q1rk1/pp2bppp/2n1bn2/3p4/3P4/2NBBN2/PP3PPP/R2Q1RK1 w - - 0 10",
        "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 1 5",
        "r1b1k2r/ppppqppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 1 6",
    ],
)
def test_quiesce_is_zero_sum(fen):
    # A minimax value seen from White must be the negation of the value seen from Black.
    board = chess.Board(fen)
    w = _quiesce(board, chess.WHITE, -MATE, MATE, 2)
    b = _quiesce(board, chess.BLACK, -MATE, MATE, 2)
    assert w == pytest.approx(-b)


def test_macos_search_does_not_grab_defended_pawn():
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    thought = choose_move(board, rng=random.Random(0), profile="macos", depth=2)
    assert thought.choice != chess.Move.from_uci("f3e5")


# Stronger walk-into-mate check than test_refuses_walk_into_mate (which cannot fail).
def test_refuses_back_rank_trap():
    board = chess.Board("4r1k1/p4ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")  # Rxa7?? Re1#
    for profile, depth in (("lite", None), ("macos", 1), ("macos", 2)):
        thought = choose_move(board.copy(), rng=random.Random(0), profile=profile, depth=depth)
        b = board.copy()
        b.push(thought.choice)
        assert not any(_mates(b, r) for r in b.legal_moves), (profile, depth, thought.choice)


def _mates(board, move):
    board.push(move)
    try:
        return board.is_checkmate()
    finally:
        board.pop()


# --- Bug 2: /think dropped the connection on valid JSON with wrong types ----------


@pytest.mark.parametrize(
    "body",
    [[1, 2], "e4", 7, None, {"depth": "3"}, {"depth": True}, {"depth": 0}, {"depth": MAX_DEPTH + 1},
     {"profile": 7}, {"profile": "turbo"}, {"fen": 12}],
)
def test_parse_think_request_rejects(body):
    with pytest.raises(ValueError):
        parse_think_request(body)


def test_parse_think_request_defaults():
    assert parse_think_request({}) == (chess.STARTING_FEN, "lite", None)
    assert parse_think_request({"profile": "MacOS", "depth": 2})[1:] == ("macos", 2)


@pytest.fixture(scope="module")
def server_url():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), ThinkHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _post(url, raw: bytes):
    req = urllib.request.Request(url + "/think", data=raw, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


@pytest.mark.parametrize(
    "raw",
    [b'{"depth":"3"}', b'{"profile":7}', b"[1,2]", b'{"depth":99}', b"notjson", b'{"fen":"nope"}',
     b'{"fen":"8/8/8/8/8/8/8/8 w - - 0 1"}', b"\xff\xfe"],
)
def test_server_returns_400_json(server_url, raw):
    status, body = _post(server_url, raw)
    assert status == 400
    assert "error" in body


def test_server_happy_path(server_url):
    status, body = _post(server_url, json.dumps({"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"}).encode())
    assert status == 200
    assert body["choice"] == "g7g5"
