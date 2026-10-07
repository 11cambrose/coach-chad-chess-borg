"""Start the macOS reinforcement loop: self-play, label by result, append JSONL.

Not PyTorch. Each game writes (fen, move, z, profile, depth) so a later linear
head can train on CPU from Coach Chad PGN + these self-play labels.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import chess

from .engine import play_game


def result_from_winner(winner: str | None, side_was_white: bool) -> float:
    if winner is None:
        return 0.0
    white_won = winner == "white"
    if side_was_white:
        return 1.0 if white_won else -1.0
    return -1.0 if white_won else 1.0


def record_game(profile: str = "macos", seed: int = 0, depth: int | None = None) -> list[dict]:
    """Play Borg vs Borg with the given profile and return labeled positions."""
    rec = play_game(
        white="borg",
        black="borg",
        seed=seed,
        profile=profile,
        depth=depth,
    )
    board = chess.Board()
    rows = []
    for san in rec["moves"]:
        move = board.parse_san(san)
        side_white = board.turn == chess.WHITE
        z = result_from_winner(rec["winner"], side_white)
        rows.append(
            {
                "fen": board.fen(),
                "move": move.uci(),
                "san": san,
                "z": z,
                "profile": profile,
                "result": rec["result"],
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )
        board.push(move)
    return rows


def run_cycle(games: int, out: Path, profile: str = "macos", seed: int = 0, depth: int | None = None) -> dict:
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("a") as fh:
        for i in range(games):
            rows = record_game(profile=profile, seed=seed + i, depth=depth)
            for row in rows:
                fh.write(json.dumps(row) + "\n")
                n += 1
    return {"games": games, "positions": n, "path": str(out), "profile": profile}
