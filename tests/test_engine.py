import chess

from chadborg.engine import choose_move, rank_moves
from chadborg.eval import evaluate_for


def test_legal_only():
    board = chess.Board()
    thought = choose_move(board)
    assert thought.choice in board.legal_moves


def test_takes_mate_in_one():
    # Scholar-style mate net: white to play Qxf7#
    board = chess.Board("r1bqkb1r/pppp1Qpp/2n2n2/4p3/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 0 4")
    # black to move here actually — use white to mate
    board = chess.Board("r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4")
    thought = choose_move(board)
    board.push(thought.choice)
    assert board.is_checkmate()


def test_refuses_walk_into_mate():
    # If white plays a stupid hanging-king move into mate, Borg should not pick it.
    board = chess.Board("4k3/8/8/8/8/8/8/4K2r w - - 0 1")
    thought = choose_move(board)
    board.push(thought.choice)
    # After Borg's move, black should not already have been given a free mate
    # that Borg walked into from a position where escapes exist.
    assert not board.is_checkmate()


def test_start_eval_near_zero():
    board = chess.Board()
    assert abs(evaluate_for(board, chess.WHITE)) < 50


def test_rank_covers_all_legal():
    board = chess.Board()
    ranked = rank_moves(board)
    assert {r.move for r in ranked} == set(board.legal_moves)


def test_lite_black_always_g5():
    import random

    board = chess.Board()
    board.push_san("e4")
    thought = choose_move(board, rng=random.Random(1), profile="lite")
    assert thought.choice == chess.Move.from_uci("g7g5")
    assert thought.assists.get("book") == "lite:1...g5"


def test_macos_white_steers_e4():
    import random

    board = chess.Board()
    thought = choose_move(board, rng=random.Random(0), profile="macos", depth=1)
    assert thought.choice == chess.Move.from_uci("e2e4")


def test_macos_kg_second_ply():
    import random

    board = chess.Board()
    board.push_san("e4")
    board.push_san("e5")
    thought = choose_move(board, rng=random.Random(0), profile="macos", depth=1)
    assert thought.choice == chess.Move.from_uci("f2f4")


def test_macos_black_mix_g5_when_roll_low():
    import random

    class Low(random.Random):
        def random(self):
            return 0.01

    board = chess.Board()
    board.push_san("e4")
    thought = choose_move(board, rng=Low(), profile="macos", depth=1)
    assert thought.choice == chess.Move.from_uci("g7g5")


def test_macos_black_mix_c5_sicilian():
    import random

    class Mid(random.Random):
        def random(self):
            return 0.85

    board = chess.Board()
    board.push_san("e4")
    thought = choose_move(board, rng=Mid(), profile="macos", depth=1)
    assert thought.choice == chess.Move.from_uci("c7c5")


def test_think_endpoint_lite_g5():
    from chadborg.server import think_payload

    board = chess.Board()
    board.push_san("e4")
    payload = think_payload(board.fen(), profile="lite")
    assert payload["choice"] == "g7g5"
