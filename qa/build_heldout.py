#!/usr/bin/env python3
"""Build the Fly-metric held-out set: positions from Coach Chad house PGNs + Stockfish
scores for EVERY legal move. Run offline (needs a Stockfish binary); the output JSONL is
committed so CI can compute best_pick / regret without Stockfish.

  python qa/build_heldout.py --pgn-dir /path/to/pgn-archive/clean \
      --stockfish /path/to/stockfish --depth 10 --out qa/data/heldout-sf19-d10.jsonl

Sampling is deterministic: plies 8..80 of each game, every 4th ply (offset by game index),
skipping positions with <2 legal moves, de-duplicated by FEN. These games must stay out of
any training buffer (rl labels are self-play only today).
"""
from __future__ import annotations

import argparse
import glob
import json
import os

import chess
import chess.engine
import chess.pgn


def sample_positions(pgn_dir: str, lo: int = 8, hi: int = 80, step: int = 4):
    seen, out = set(), []
    for gi, path in enumerate(sorted(glob.glob(os.path.join(pgn_dir, "*.pgn")))):
        with open(path) as fh:
            game = chess.pgn.read_game(fh)
        if game is None:
            continue
        board = game.board()
        for ply, move in enumerate(game.mainline_moves(), start=1):
            board.push(move)
            if ply < lo or ply > hi or (ply + gi) % step:
                continue
            if board.is_game_over() or board.legal_moves.count() < 2:
                continue
            key = board.fen()
            if key in seen:
                continue
            seen.add(key)
            out.append({"fen": key, "src": f"{os.path.basename(path)}#ply{ply}"})
    return out


def score_all_moves(engine, board: chess.Board, depth: int) -> dict[str, int]:
    n = board.legal_moves.count()
    infos = engine.analyse(board, chess.engine.Limit(depth=depth), multipv=n)
    scores = {}
    for info in infos:
        mv = info["pv"][0]
        scores[mv.uci()] = info["score"].pov(board.turn).score(mate_score=10000)
    missing = [m for m in board.legal_moves if m.uci() not in scores]
    for m in missing:  # multipv should cover all moves; fall back to a 1-move search
        info = engine.analyse(board, chess.engine.Limit(depth=depth), root_moves=[m])
        scores[m.uci()] = info["score"].pov(board.turn).score(mate_score=10000)
    return scores


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn-dir", required=True)
    ap.add_argument("--stockfish", required=True)
    ap.add_argument("--depth", type=int, default=10)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    positions = sample_positions(a.pgn_dir)
    engine = chess.engine.SimpleEngine.popen_uci(a.stockfish)
    engine.configure({"Threads": 1, "Hash": 64})
    name = engine.id.get("name", "stockfish")
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as fh:
        for p in positions:
            board = chess.Board(p["fen"])
            p["scores_cp"] = score_all_moves(engine, board, a.depth)
            p["engine"] = f"{name} depth {a.depth}"
            fh.write(json.dumps(p) + "\n")
    engine.quit()
    print(f"wrote {len(positions)} positions to {a.out}")


if __name__ == "__main__":
    main()
