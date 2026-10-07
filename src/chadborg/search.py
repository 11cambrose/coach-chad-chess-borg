"""Search depths for the two Borgs.

lite  — Fly 1-ply rank (depth 1), cheap enough for a Railway /think box.
macos — beast mode: alpha-beta to `depth` with capture/check quiescence.
        This is the start of the RL cycle (self-play writes labeled positions).
"""

from __future__ import annotations

import chess

from .eval import evaluate_for

MATE = 100_000.0


def _terminal(board: chess.Board, root_color: chess.Color) -> float | None:
    if board.is_checkmate():
        return -MATE if board.turn == root_color else MATE
    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
        return 0.0
    return None


def _ordered(board: chess.Board) -> list[chess.Move]:
    moves = list(board.legal_moves)
    def key(m: chess.Move) -> tuple:
        cap = board.is_capture(m)
        chk = board.gives_check(m)
        promo = m.promotion is not None
        return (0 if promo else 1, 0 if chk else 1, 0 if cap else 1)
    moves.sort(key=key)
    return moves


def _quiesce(board: chess.Board, root_color: chess.Color, alpha: float, beta: float, qply: int) -> float:
    """Capture/check/promotion quiescence, scored from root_color's view.

    Minimax-consistent: the side to move picks what is best for *itself*. (0.4.0 always
    maximized for root_color, so at opponent nodes it ignored the opponent's captures.)
    """
    term = _terminal(board, root_color)
    if term is not None:
        return term
    stand = evaluate_for(board, root_color)
    if qply <= 0:
        return stand
    maximizing = board.turn == root_color
    if maximizing:
        if stand >= beta:
            return stand
        alpha = max(alpha, stand)
    else:
        if stand <= alpha:
            return stand
        beta = min(beta, stand)
    for move in _ordered(board):
        if not (board.is_capture(move) or board.gives_check(move) or move.promotion):
            continue
        board.push(move)
        score = _quiesce(board, root_color, alpha, beta, qply - 1)
        board.pop()
        if maximizing:
            if score >= beta:
                return score
            alpha = max(alpha, score)
        else:
            if score <= alpha:
                return score
            beta = min(beta, score)
    return alpha if maximizing else beta


def alphabeta(
    board: chess.Board,
    root_color: chess.Color,
    depth: int,
    alpha: float,
    beta: float,
    qply: int = 2,
) -> float:
    term = _terminal(board, root_color)
    if term is not None:
        return term + (0.01 * depth if term > 0 else -0.01 * depth)
    if depth <= 0:
        return _quiesce(board, root_color, alpha, beta, qply)
    maximizing = board.turn == root_color
    best = -MATE if maximizing else MATE
    for move in _ordered(board):
        board.push(move)
        score = alphabeta(board, root_color, depth - 1, alpha, beta, qply)
        board.pop()
        if maximizing:
            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if alpha >= beta:
                break
        else:
            if score < best:
                best = score
            if best < beta:
                beta = best
            if alpha >= beta:
                break
    return best


def search_root(board: chess.Board, depth: int, qply: int = 2) -> list[tuple[chess.Move, float, bool, bool]]:
    """Return legal moves scored from the side-to-move view, best first."""
    us = board.turn
    out: list[tuple[chess.Move, float, bool, bool]] = []
    for move in _ordered(board):
        san_safe = True
        board.push(move)
        gives_mate = board.is_checkmate()
        walks = False
        if not gives_mate:
            for reply in board.legal_moves:
                board.push(reply)
                if board.is_checkmate():
                    walks = True
                    board.pop()
                    break
                board.pop()
        if gives_mate:
            score = MATE
        else:
            score = alphabeta(board, us, max(depth - 1, 0), -MATE, MATE, qply)
        board.pop()
        out.append((move, score, gives_mate, walks))
    out.sort(key=lambda t: t[1], reverse=True)
    return out
