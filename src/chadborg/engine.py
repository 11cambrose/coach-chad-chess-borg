"""Coach Chad Borg — Fly-style legal-move ranker.

Pipeline copied from the working Fly Chess app
(https://flychess-hq.vercel.app / flychess-production.up.railway.app):

  1. Enumerate legal moves only.
  2. Push each move and score the *resulting* board (1-ply rollout).
  3. Rank and pick the highest.
  4. Hard assists:
       - if a move is checkmate, play it
       - if a move walks into mate-in-1, never play it
  5. On held-out style scoring we measure 'closer to best than random'
     rather than pretending we have a calibrated FIDE Elo from 4 GitHub-Action games.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import chess

from .eval import evaluate_for
from .openings import pick_book_move


@dataclass
class RankedMove:
    move: chess.Move
    uci: str
    san: str
    score: float
    is_mate: bool
    gives_mate: bool
    walks_into_mate: bool


@dataclass
class ThinkResult:
    choice: chess.Move
    ranked: list[RankedMove]
    assists: dict = field(default_factory=dict)


def _opponent_has_mate_in_one(board: chess.Board) -> bool:
    for reply in board.legal_moves:
        board.push(reply)
        mated = board.is_checkmate()
        board.pop()
        if mated:
            return True
    return False


def rank_moves(board: chess.Board, rng: random.Random | None = None) -> list[RankedMove]:
    if rng is None:
        rng = random.Random()
    us = board.turn
    ranked: list[RankedMove] = []
    for move in board.legal_moves:
        san = board.san(move)
        board.push(move)
        gives_mate = board.is_checkmate()
        walks = False if gives_mate else _opponent_has_mate_in_one(board)
        score = evaluate_for(board, us)
        # Tiny jitter so equal-eval lines do not lock the same book line forever
        score += rng.uniform(-0.5, 0.5)
        board.pop()
        ranked.append(
            RankedMove(
                move=move,
                uci=move.uci(),
                san=san,
                score=score,
                is_mate=gives_mate,
                gives_mate=gives_mate,
                walks_into_mate=walks,
            )
        )
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def choose_move(
    board: chess.Board,
    rng: random.Random | None = None,
    profile: str = "lite",
    depth: int | None = None,
) -> ThinkResult:
    if not any(board.legal_moves):
        raise ValueError("no legal moves")
    if rng is None:
        rng = random.Random()
    profile = (profile or "lite").lower()
    if depth is None:
        depth = 3 if profile == "macos" else 1

    book = pick_book_move(board, profile, rng)
    if book is not None:
        ranked = rank_moves(board, rng=rng)
        return ThinkResult(
            choice=book.move,
            ranked=ranked,
            assists={"book": book.reason, "profile": profile, "depth": depth},
        )

    if depth <= 1:
        ranked = rank_moves(board, rng=rng)
    else:
        from .search import search_root

        scored = search_root(board, depth=depth, qply=2)
        ranked = []
        for move, score, gives_mate, walks in scored:
            ranked.append(
                RankedMove(
                    move=move,
                    uci=move.uci(),
                    san=board.san(move),
                    score=score,
                    is_mate=gives_mate,
                    gives_mate=gives_mate,
                    walks_into_mate=walks,
                )
            )
    mates = [r for r in ranked if r.gives_mate]
    if mates:
        return ThinkResult(
            choice=mates[0].move,
            ranked=ranked,
            assists={"take_mate": True, "profile": profile, "depth": depth},
        )
    safe = [r for r in ranked if not r.walks_into_mate]
    pool = safe if safe else ranked
    return ThinkResult(
        choice=pool[0].move,
        ranked=ranked,
        assists={
            "refuse_mate_in_one": bool(safe) and any(r.walks_into_mate for r in ranked),
            "profile": profile,
            "depth": depth,
        },
    )


def play_game(
    white="borg",
    black="random",
    max_moves: int = 200,
    seed: int | None = None,
    profile: str = "lite",
    depth: int | None = None,
) -> dict:
    rng = random.Random(seed)
    board = chess.Board()
    moves = []
    while not board.is_game_over() and len(moves) < max_moves:
        role = white if board.turn == chess.WHITE else black
        if role == "borg":
            move = choose_move(board, rng=rng, profile=profile, depth=depth).choice
        else:
            move = rng.choice(list(board.legal_moves))
        moves.append(board.san(move))
        board.push(move)
    outcome = board.outcome()
    if outcome is None or outcome.winner is None:
        result = "1/2-1/2"
        winner = None
    elif outcome.winner == chess.WHITE:
        result = "1-0"
        winner = "white"
    else:
        result = "0-1"
        winner = "black"
    return {
        "result": result,
        "winner": winner,
        "moves": moves,
        "fen": board.fen(),
        "termination": None if outcome is None else str(outcome.termination),
        "ply": len(moves),
    }


def match_score(games: int = 20, seed: int = 0, profile: str = "lite") -> dict:
    """Borg (alternating color) vs random legal. Fly-style score, not Elo cosplay."""
    wins = draws = losses = 0
    for i in range(games):
        borg_white = i % 2 == 0
        rec = play_game(
            white="borg" if borg_white else "random",
            black="random" if borg_white else "borg",
            seed=seed + i,
            profile=profile,
        )
        if rec["winner"] is None:
            draws += 1
        elif (rec["winner"] == "white") == borg_white:
            wins += 1
        else:
            losses += 1
    total = wins + draws + losses
    score = (wins + 0.5 * draws) / total if total else 0.0
    # Rough Elo vs random (~200-400 true strength). Random ≈ 800 club floor
    # if we treat "always-legal random" as 400.
    if score <= 0.0:
        elo_vs_random400 = 400.0
    elif score >= 1.0:
        elo_vs_random400 = 400.0 + 800.0
    else:
        elo_vs_random400 = 400.0 + 400.0 * math.log10(score / (1.0 - score))
    return {
        "games": total,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "score": round(score, 4),
        "est_elo_vs_random400": round(elo_vs_random400, 1),
    }
