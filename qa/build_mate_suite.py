#!/usr/bin/env python3
"""Build the mate-assist suite (python-chess only, no engine needed).

  take  - side to move has at least one mate-in-1; pass = engine plays a mating move
  avoid - side to move has no mate-in-1, at least one legal move lets the opponent mate
          in 1, and at least one safe move exists; pass = engine's move allows no mate-in-1

Sources: hand-written classics + positions mined from house PGNs (every ply).
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import chess
import chess.pgn

HAND = [
    ("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", "back-rank Rd8#"),
    ("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "scholar Qxf7#"),
    ("rnbqkbnr/pppp1ppp/8/4p3/6P1/5P2/PPPPP2P/RNBQKBNR b KQkq - 0 2", "fool's mate Qh4#"),
    ("k7/8/1K6/8/8/8/8/7Q w - - 0 1", "queen Qb7#/Qh8#"),
    ("6k1/8/6K1/8/8/8/8/R7 w - - 0 1", "rook ladder Ra8#"),
    ("4r1k1/p4ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "back-rank trap: Rxa7?? Re1#"),
    ("6k1/5ppp/8/8/8/8/r4PPP/1R4K1 w - - 0 1", "back-rank Rb8#"),
    ("r5k1/5ppp/8/8/8/8/5PPP/1Q4K1 b - - 0 1", "black rook must guard back rank vs Qb8+"),
]


def mates(board: chess.Board) -> list[chess.Move]:
    out = []
    for m in board.legal_moves:
        board.push(m)
        if board.is_checkmate():
            out.append(m)
        board.pop()
    return out


def allows_mate(board: chess.Board, move: chess.Move) -> bool:
    board.push(move)
    try:
        return bool(mates(board))
    finally:
        board.pop()


def classify(fen: str) -> dict | None:
    board = chess.Board(fen)
    if board.is_game_over():
        return None
    mating = mates(board)
    if mating:
        return {"kind": "take", "fen": fen, "mates": sorted(m.uci() for m in mating)}
    bad = [m for m in board.legal_moves if allows_mate(board, m)]
    if bad and len(bad) < board.legal_moves.count():
        return {"kind": "avoid", "fen": fen, "losing": sorted(m.uci() for m in bad),
                "legal": board.legal_moves.count()}
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn-glob", action="append", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows, seen = [], set()
    for fen, label in HAND:
        c = classify(fen)
        if c and fen not in seen:
            seen.add(fen)
            rows.append(c | {"src": f"hand:{label}"})
    for pattern in a.pgn_glob:
        for path in sorted(glob.glob(pattern)):
            with open(path) as fh:
                while (game := chess.pgn.read_game(fh)) is not None:
                    board = game.board()
                    for ply, move in enumerate(game.mainline_moves(), start=1):
                        board.push(move)
                        fen = board.fen()
                        if fen in seen:
                            continue
                        c = classify(fen)
                        if c:
                            seen.add(fen)
                            rows.append(c | {"src": f"{os.path.basename(path)}#ply{ply}"})
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"take={sum(r['kind']=='take' for r in rows)} avoid={sum(r['kind']=='avoid' for r in rows)} -> {a.out}")


if __name__ == "__main__":
    main()
