"""CLI for Coach Chad Borg — lite (Railway /think) and macos (beast search + RL)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import chess

from .engine import choose_move, match_score, play_game, rank_moves
from .rl import run_cycle
from .server import serve, think_payload


def _profile_kwargs(args: argparse.Namespace) -> dict:
    depth = getattr(args, "depth", None)
    return {"profile": getattr(args, "profile", "lite"), "depth": depth if depth else None}


def cmd_think(args: argparse.Namespace) -> None:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    result = choose_move(board, **_profile_kwargs(args))
    payload = {
        "fen": board.fen(),
        "choice": result.choice.uci(),
        "choice_san": board.san(result.choice),
        "assists": result.assists,
        "top": [
            {
                "uci": r.uci,
                "san": r.san,
                "score": round(r.score, 2),
                "gives_mate": r.gives_mate,
                "walks_into_mate": r.walks_into_mate,
            }
            for r in result.ranked[: args.top]
        ],
    }
    print(json.dumps(payload, indent=2))


def cmd_play(args: argparse.Namespace) -> None:
    board = chess.Board()
    human_white = args.color == "white"
    print(f"Coach Chad Borg [{args.profile}]. SAN or UCI. quit to leave.\n")
    while not board.is_game_over():
        print(board, "\n")
        human_turn = board.turn == (chess.WHITE if human_white else chess.BLACK)
        if human_turn:
            raw = input("Your move: ").strip()
            if raw.lower() in {"quit", "exit"}:
                return
            move = None
            try:
                move = board.parse_san(raw)
            except ValueError:
                try:
                    move = chess.Move.from_uci(raw)
                except ValueError:
                    move = None
            if move is None or move not in board.legal_moves:
                print("Illegal. Try again.")
                continue
        else:
            thought = choose_move(board, **_profile_kwargs(args))
            book = thought.assists.get("book", "")
            extra = f"  book={book}" if book else ""
            print(f"Borg plays {board.san(thought.choice)}  (score {thought.ranked[0].score:.1f}){extra}")
            move = thought.choice
        board.push(move)
    print(board)
    print("Result:", board.result(), board.outcome())


def cmd_selfplay(args: argparse.Namespace) -> None:
    rec = play_game(white="borg", black="borg", seed=args.seed, **_profile_kwargs(args))
    print(json.dumps(rec, indent=2))


def cmd_eval(args: argparse.Namespace) -> None:
    stats = match_score(games=args.games, seed=args.seed, profile=args.profile)
    stats["profile"] = args.profile
    out = Path(args.out) if args.out else None
    print(json.dumps(stats, indent=2))
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if out.exists():
            history = json.loads(out.read_text())
        history.append(stats)
        out.write_text(json.dumps(history, indent=2))


def cmd_rank(args: argparse.Namespace) -> None:
    board = chess.Board(args.fen) if args.fen else chess.Board()
    ranked = rank_moves(board)
    for i, r in enumerate(ranked, 1):
        flags = []
        if r.gives_mate:
            flags.append("MATE")
        if r.walks_into_mate:
            flags.append("SUICIDE")
        print(f"{i:2d}  {r.san:<8} {r.score:8.1f}  {' '.join(flags)}")


def cmd_serve(args: argparse.Namespace) -> None:
    serve(host=args.host, port=args.port)


def cmd_rl(args: argparse.Namespace) -> None:
    stats = run_cycle(
        games=args.games,
        out=Path(args.out),
        profile=args.profile,
        seed=args.seed,
        depth=args.depth or None,
    )
    print(json.dumps(stats, indent=2))


def _add_profile(p: argparse.ArgumentParser, default: str = "lite") -> None:
    p.add_argument("--profile", choices=["lite", "macos", "default"], default=default)
    p.add_argument("--depth", type=int, default=0, help="0 = profile default (lite=1, macos=3)")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="chadborg",
        description="Coach Chad Borg — lite /think (1...g5) and macos beast (KG + 80/10/10 + search + RL)",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("think", help="rank legal moves from a FEN")
    t.add_argument("--fen", default="")
    t.add_argument("--top", type=int, default=8)
    _add_profile(t, "lite")
    t.set_defaults(func=cmd_think)

    r = sub.add_parser("rank", help="print ranked legal moves (1-ply, no book)")
    r.add_argument("--fen", default="")
    r.set_defaults(func=cmd_rank)

    pl = sub.add_parser("play", help="human vs Borg")
    pl.add_argument("--color", choices=["white", "black"], default="white")
    _add_profile(pl, "lite")
    pl.set_defaults(func=cmd_play)

    s = sub.add_parser("selfplay", help="Borg vs Borg game")
    s.add_argument("--seed", type=int, default=0)
    _add_profile(s, "lite")
    s.set_defaults(func=cmd_selfplay)

    e = sub.add_parser("eval", help="Borg vs random legal")
    e.add_argument("--games", type=int, default=20)
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--out", default="ratings/history.json")
    _add_profile(e, "lite")
    e.set_defaults(func=cmd_eval)

    sv = sub.add_parser("serve", help="lite Railway-style POST /think")
    sv.add_argument("--host", default="0.0.0.0")
    sv.add_argument("--port", type=int, default=8787)
    sv.set_defaults(func=cmd_serve)

    rl = sub.add_parser("rl", help="macos self-play cycle → JSONL labels")
    rl.add_argument("--games", type=int, default=4)
    rl.add_argument("--seed", type=int, default=0)
    rl.add_argument("--out", default="ratings/rl_buffer.jsonl")
    _add_profile(rl, "macos")
    rl.set_defaults(func=cmd_rl)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
