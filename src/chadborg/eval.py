"""1-ply position scorer — the Fly Chess insight without a 164k-cell connectome.

Fly Chess does this:
  for each legal move:
      push the move
      inject the resulting board into sensory neurons
      read motor neurons
      rank
  pick the max
  hard assists: take mate if present; refuse mate-in-1

We do the same loop with a cheap, portable feature ranker instead of MaleCNS.
"""

from __future__ import annotations

import chess

PIECE_VALUE = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

CENTER = {chess.D4, chess.E4, chess.D5, chess.E5}
EXTENDED = CENTER | {
    chess.C3, chess.D3, chess.E3, chess.F3,
    chess.C4, chess.F4, chess.C5, chess.F5,
    chess.C6, chess.D6, chess.E6, chess.F6,
}


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(PIECE_VALUE[p.piece_type] for p in board.piece_map().values() if p.color == color)


def mobility(board: chess.Board, color: chess.Color) -> int:
    if board.turn == color:
        return board.legal_moves.count()
    # Flip turn cheaply via a copy only when needed
    tmp = board.copy(stack=False)
    tmp.turn = color
    if tmp.is_check():
        # If the side to score is in check on a fake turn flip, mobility is the
        # escape set — still a useful signal.
        pass
    try:
        return tmp.legal_moves.count()
    except ValueError:
        return 0


def hanging_penalty(board: chess.Board, color: chess.Color) -> int:
    """Penalty for our hanging pieces; bonus for theirs."""
    score = 0
    for sq, piece in board.piece_map().items():
        attackers = board.attackers(not piece.color, sq)
        defenders = board.attackers(piece.color, sq)
        if attackers and not defenders:
            val = PIECE_VALUE[piece.piece_type]
            score += -val if piece.color == color else val
        elif attackers and defenders:
            cheapest_atk = min(PIECE_VALUE[board.piece_type_at(a)] for a in attackers)
            if cheapest_atk < PIECE_VALUE[piece.piece_type] and not defenders:
                pass
            elif cheapest_atk < PIECE_VALUE[piece.piece_type] and len(attackers) > len(defenders):
                val = PIECE_VALUE[piece.piece_type] // 2
                score += -val if piece.color == color else val
    return score


def king_safety(board: chess.Board, color: chess.Color) -> int:
    ksq = board.king(color)
    if ksq is None:
        return -10_000
    attackers = board.attackers(not color, ksq)
    return -80 * len(attackers)


def center_control(board: chess.Board, color: chess.Color) -> int:
    s = 0
    for sq in EXTENDED:
        piece = board.piece_at(sq)
        if piece and piece.color == color:
            s += 12 if sq in CENTER else 6
        if board.is_attacked_by(color, sq):
            s += 3
    return s


def development(board: chess.Board, color: chess.Color) -> int:
    s = 0
    back = 0 if color == chess.WHITE else 7
    for piece_type, files in ((chess.KNIGHT, (1, 6)), (chess.BISHOP, (2, 5))):
        for f in files:
            sq = chess.square(f, back)
            piece = board.piece_at(sq)
            if piece is None or piece.piece_type != piece_type or piece.color != color:
                s += 8  # developed (or missing — already out)
    # Castling rights leftover is a small plus; having already castled is better
    if board.has_castling_rights(color):
        s += 6
    ksq = board.king(color)
    if ksq is not None:
        file = chess.square_file(ksq)
        if file in (1, 2, 6, 5) and chess.square_rank(ksq) == back:
            s += 18  # tucked
    return s


def passed_pawns(board: chess.Board, color: chess.Color) -> int:
    s = 0
    them = not color
    for sq in board.pieces(chess.PAWN, color):
        file = chess.square_file(sq)
        rank = chess.square_rank(sq)
        blocked = False
        ahead = range(rank + 1, 8) if color == chess.WHITE else range(rank - 1, -1, -1)
        for r in ahead:
            for f in (file - 1, file, file + 1):
                if 0 <= f <= 7:
                    p = board.piece_at(chess.square(f, r))
                    if p and p.piece_type == chess.PAWN and p.color == them:
                        blocked = True
                        break
            if blocked:
                break
        if not blocked:
            advance = rank if color == chess.WHITE else 7 - rank
            s += 10 + 8 * advance
    return s


def evaluate_for(board: chess.Board, color: chess.Color) -> float:
    """Static score from `color`'s point of view. Larger is better for color."""
    if board.is_checkmate():
        # Side to move is mated
        return -100_000.0 if board.turn == color else 100_000.0
    if board.is_stalemate() or board.is_insufficient_material() or board.can_claim_draw():
        return 0.0

    score = 0.0
    score += material(board, color) - material(board, not color)
    score += 2.0 * (mobility(board, color) - mobility(board, not color))
    score += 0.8 * hanging_penalty(board, color)
    score += king_safety(board, color) - king_safety(board, not color)
    score += center_control(board, color) - center_control(board, not color)
    score += development(board, color) - development(board, not color)
    score += passed_pawns(board, color) - passed_pawns(board, not color)
    if board.is_check() and board.turn != color:
        score += 25.0
    if board.is_check() and board.turn == color:
        score -= 25.0
    return float(score)
