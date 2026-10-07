"""Opening personalities for Coach Chad Borg.

lite   — Black's first *reply* (after White has moved) is always 1...g5 when legal.
macos  — White almost always steers King's Gambit (1.e4, then 2.f4 after 1...e5).
         Black's first *reply*: 80% 1...g5, 10% 1...c5, 10% random legal.
         Black never moves first. The mix fires only when it is Black to move and
         exactly one ply has been played (White already went).
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import chess

PROFILES = ("default", "lite", "macos")

# "Almost always" for the macOS King's Gambit steer.
KG_E4_WEIGHT = 0.95
KG_F4_WEIGHT = 0.95

BLACK_FIRST_REPLY = {
    "g5": 0.80,
    "c5": 0.10,
    "random": 0.10,
}


@dataclass(frozen=True)
class BookHit:
    move: chess.Move
    reason: str


def _parse_legal(board: chess.Board, san: str) -> chess.Move | None:
    try:
        move = board.parse_san(san)
    except ValueError:
        return None
    return move if move in board.legal_moves else None


def _is_black_first_reply(board: chess.Board) -> bool:
    # Black to move after White's opening ply. Never "Black goes first."
    return board.turn == chess.BLACK and board.ply() == 1


def _is_white_first_move(board: chess.Board) -> bool:
    return board.turn == chess.WHITE and board.ply() == 0


def _is_kg_second_ply(board: chess.Board) -> bool:
    """White to play move 2 after 1.e4 e5."""
    if board.turn != chess.WHITE or board.ply() != 2:
        return False
    return board.board_fen() == "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR"


def pick_book_move(board: chess.Board, profile: str, rng: random.Random) -> BookHit | None:
    profile = (profile or "default").lower()
    if profile not in PROFILES:
        profile = "default"
    if profile == "default":
        return None

    if profile == "lite" and _is_black_first_reply(board):
        move = _parse_legal(board, "g5")
        if move is not None:
            return BookHit(move, "lite:1...g5")
        return None

    if profile != "macos":
        return None

    if _is_white_first_move(board):
        e4 = _parse_legal(board, "e4")
        if e4 is not None and rng.random() < KG_E4_WEIGHT:
            return BookHit(e4, "macos:1.e4 (King's Gambit steer)")
        return None

    if _is_kg_second_ply(board):
        f4 = _parse_legal(board, "f4")
        if f4 is not None and rng.random() < KG_F4_WEIGHT:
            return BookHit(f4, "macos:2.f4 King's Gambit")
        return None

    if _is_black_first_reply(board):
        roll = rng.random()
        if roll < BLACK_FIRST_REPLY["g5"]:
            move = _parse_legal(board, "g5")
            if move is not None:
                return BookHit(move, "macos:1...g5 Borg (80%)")
        elif roll < BLACK_FIRST_REPLY["g5"] + BLACK_FIRST_REPLY["c5"]:
            move = _parse_legal(board, "c5")
            if move is not None:
                d4 = board.piece_at(chess.D4)
                family = "Old Benoni" if d4 and d4.piece_type == chess.PAWN and d4.color == chess.WHITE else "Sicilian"
                return BookHit(move, f"macos:1...c5 {family} (10%)")
        legal = list(board.legal_moves)
        if legal:
            return BookHit(rng.choice(legal), "macos:1...random (10%)")

    # Continuations — only when the move is legal. Search still owns tactics.
    hit = _macos_continuation(board)
    if hit is not None and rng.random() < 0.85:
        return hit
    return None


def _macos_continuation(board: chess.Board) -> BookHit | None:
    """Small family book after the first-move mix."""
    if board.fullmove_number > 8:
        return None
    placement = board.board_fen()
    # King's Gambit accepted: 1.e4 e5 2.f4 exf4 — White develops Nf3
    if placement == "rnbqkbnr/pppp1ppp/8/8/4Pp2/8/PPPP2PP/RNBQKBNR" and board.turn == chess.WHITE:
        m = _parse_legal(board, "Nf3")
        if m:
            return BookHit(m, "macos:KG accepted Nf3")
    # Sicilian: 1.e4 c5 — White Nf3
    if placement == "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR" and board.turn == chess.WHITE:
        m = _parse_legal(board, "Nf3")
        if m:
            return BookHit(m, "macos:Sicilian Nf3")
    # French: 1.e4 e6 — White d4
    if placement == "rnbqkbnr/pppp1ppp/4p3/8/4P3/8/PPPP1PPP/RNBQKBNR" and board.turn == chess.WHITE:
        m = _parse_legal(board, "d4")
        if m:
            return BookHit(m, "macos:French d4")
    # Old Benoni: 1.d4 c5 — White d5
    if placement == "rnbqkbnr/pp1ppppp/8/2p5/3P4/8/PPP1PPPP/RNBQKBNR" and board.turn == chess.WHITE:
        m = _parse_legal(board, "d5")
        if m:
            return BookHit(m, "macos:Old Benoni d5")
    # Borg confirmed: 1.e4 g5 — if we are White, kick the g-pawn ideas with d4
    if placement == "rnbqkbnr/pppppp1p/8/6p1/4P3/8/PPPP1PPP/RNBQKBNR" and board.turn == chess.WHITE:
        m = _parse_legal(board, "d4")
        if m:
            return BookHit(m, "macos:vs Borg d4")
    return None
