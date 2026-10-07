#!/usr/bin/env python3
"""Coach Chad Borg QA harness (prototype, 2026-10-06).

Engine-agnostic: every Borg build is wrapped as an adapter with choose(board) -> chess.Move.
Adapters: random | chadborg:<profile>[:depth] | think:<profile>@<url> | uci:<path>[:depth]
          | chesszero:<checkpoint.pt>[:sims]   (legacy AlphaZero fork)
          chadborg = in-process src/chadborg; think = the same engine over POST /think.
For chadborg-specific metrics (g5 rates, mate assists, Fly best_pick/regret) see chadborg_qa.py.

Checks per run:
  1. enumerator sanity  - python-chess perft on fixed positions vs known counts
  2. legality           - every engine move must be in board.legal_moves (an illegal move = hard FAIL)
  3. book adherence     - with --expect-black-first g7g5, Black's first move must be ...g5
  4. opening suite      - fixed Borg suite starting 1...g5 (+ Sicilian/Benoni/French/KG controls)
  5. regression match   - candidate vs fixed opponent (Stockfish at fixed depth, or random) from the suite
Appends one row to results.csv (versioned) and writes a JSON detail file.
"""
from __future__ import annotations
import argparse, csv, datetime as dt, json, os, random, subprocess, sys, time
from pathlib import Path
import chess, chess.engine, chess.pgn

SUITE = {  # name: SAN moves already played (candidate then plays from here)
    "borg-vs-e4":      ["e4", "g5"],
    "borg-vs-d4":      ["d4", "g5"],
    "borg-vs-c4":      ["c4", "g5"],
    "borg-vs-Nf3":     ["Nf3", "g5"],
    "borg-vs-f4":      ["f4", "g5"],
    "borg-Bxg5-line":  ["d4", "g5", "Bxg5"],
    "borg-e4-d4-h6":   ["e4", "g5", "d4", "h6"],
    "borg-e4-d4-Bg7":  ["e4", "g5", "d4", "Bg7"],
    "kings-gambit":    ["e4", "e5", "f4"],
    "sicilian":        ["e4", "c5"],
    "old-benoni":      ["d4", "c5"],
    "french":          ["e4", "e6"],
}
FIRST_WHITE = ["e4", "d4", "c4", "Nf3", "f4", "g3", "b3", "e3", "Nc3", "a3"]  # book probe for ...g5
PERFT = [  # (fen, depth, expected nodes) - standard published perft values
    (chess.STARTING_FEN, 3, 8902),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", 2, 2039),  # "Kiwipete"
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", 3, 2812),
]

def perft(b: chess.Board, d: int) -> int:
    if d == 0: return 1
    n = 0
    for m in b.legal_moves:
        b.push(m); n += perft(b, d - 1); b.pop()
    return n

class Random:
    name = "random"
    def __init__(self, seed=0): self.r = random.Random(seed)
    def choose(self, b): return self.r.choice(list(b.legal_moves))
    def close(self): pass

class ChessZero:
    def __init__(self, path, sims=16):
        from chesszero.checkpoint import load_checkpoint
        from chesszero.agent import MCTSAgent
        net, cfg, _ = load_checkpoint(path, device="cpu")
        self.agent = MCTSAgent(net, cfg, simulations=int(sims)); self.name = f"chesszero:{Path(path).name}:{sims}"
    def choose(self, b): return self.agent.choose_move(b.copy(), temperature=0.0)
    def close(self): pass

class UCI:
    def __init__(self, path, depth=4):
        self.e = chess.engine.SimpleEngine.popen_uci(path); self.depth = int(depth); self.name = f"uci:{Path(path).name}:d{depth}"
    def choose(self, b): return self.e.play(b, chess.engine.Limit(depth=self.depth)).move
    def close(self): self.e.quit()

class ChadBorg:
    def __init__(self, profile="lite", depth=None, seed=0):
        from chadborg.engine import choose_move
        self._choose, self.profile = choose_move, profile
        self.depth = int(depth) if depth else None
        self.r = random.Random(seed); self.name = f"chadborg:{profile}" + (f":{depth}" if depth else "")
    def choose(self, b): return self._choose(b.copy(), rng=self.r, profile=self.profile, depth=self.depth).choice
    def close(self): pass

class Think:
    def __init__(self, url, profile="lite"):
        self.url, self.profile = url, profile; self.name = f"think:{profile}"
    def choose(self, b):
        import urllib.request
        req = urllib.request.Request(self.url, data=json.dumps({"fen": b.fen(), "profile": self.profile}).encode(), headers={"Content-Type": "application/json"})
        out = json.load(urllib.request.urlopen(req, timeout=30))
        return chess.Move.from_uci(out.get("choice") or out.get("move") or out.get("uci"))
    def close(self): pass

def adapter(spec: str, seed=0):
    kind, _, rest = spec.partition(":")
    parts = rest.split(":") if rest else []
    if kind == "random": return Random(seed)
    if kind == "chesszero": return ChessZero(*parts)
    if kind == "uci": return UCI(*parts)
    if kind == "chadborg": return ChadBorg(*(parts or ["lite"]), seed=seed)
    if kind == "think":  # think:<profile>@<url>  e.g. think:lite@http://127.0.0.1:8787/think
        prof, _, url = rest.partition("@"); return Think(url, prof or "lite")
    raise SystemExit(f"unknown adapter {spec}")

def play(cand, opp, start_sans, cand_white, max_plies, illegal_log, tag):
    b = chess.Board()
    for s in start_sans: b.push_san(s)
    game = chess.pgn.Game.from_board(b); game.headers.update({"Event": f"Borg QA {tag}", "White": cand.name if cand_white else opp.name, "Black": opp.name if cand_white else cand.name})
    while not b.is_game_over(claim_draw=True) and b.ply() < max_plies:
        mover = cand if (b.turn == chess.WHITE) == cand_white else opp
        try: m = mover.choose(b)
        except Exception as e: illegal_log.append({"tag": tag, "fen": b.fen(), "engine": mover.name, "error": repr(e)}); return 0.0 if mover is cand else 1.0, b, "error"
        if m not in b.legal_moves:
            illegal_log.append({"tag": tag, "fen": b.fen(), "engine": mover.name, "move": str(m)})
            return (0.0 if mover is cand else 1.0), b, "illegal"
        b.push(m)
    res = b.result(claim_draw=True)
    if res == "*": return 0.5, b, "adjudicated-draw(max plies)"
    s = 1.0 if res == "1-0" else 0.0 if res == "0-1" else 0.5
    return (s if cand_white else 1 - s), b, res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True); ap.add_argument("--version", required=True)
    ap.add_argument("--opponent", default="random"); ap.add_argument("--games-per-opening", type=int, default=2)
    ap.add_argument("--max-plies", type=int, default=160); ap.add_argument("--expect-black-first", default=None, help="e.g. g7g5 for Borg lite")
    ap.add_argument("--suite", default=",".join(SUITE)); ap.add_argument("--out-dir", default="results"); ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); detail = {"version": a.version, "candidate": a.candidate, "opponent": a.opponent, "ran_at": dt.datetime.now().astimezone().isoformat()}
    # 1 enumerator sanity
    detail["perft"] = [{"fen": f, "depth": d, "want": w, "got": perft(chess.Board(f), d)} for f, d, w in PERFT]
    perft_ok = all(p["want"] == p["got"] for p in detail["perft"])
    cand = adapter(a.candidate, a.seed); opp = adapter(a.opponent, a.seed + 1)
    illegal = []
    # 3 book adherence
    book = None
    if a.expect_black_first:
        hits = []
        for w in FIRST_WHITE:
            b = chess.Board(); b.push_san(w); m = cand.choose(b)
            if m not in b.legal_moves: illegal.append({"tag": f"book-{w}", "fen": b.fen(), "engine": cand.name, "move": str(m)})
            hits.append({"white": w, "reply": str(m), "ok": str(m) == a.expect_black_first})
        book = {"expect": a.expect_black_first, "probes": hits, "rate": sum(h["ok"] for h in hits) / len(hits)}
    detail["book"] = book
    # 4+5 suite games
    games, score, plies = [], 0.0, 0
    pgn_path = out / f"{a.version}-games.pgn"
    with open(pgn_path, "w") as pg:
        for name in a.suite.split(","):
            for g in range(a.games_per_opening):
                cw = g % 2 == 0
                s, b, how = play(cand, opp, SUITE[name], cw, a.max_plies, illegal, f"{name}#{g}")
                score += s; plies += b.ply(); games.append({"opening": name, "cand_white": cw, "score": s, "result": how, "plies": b.ply()})
                print(chess.pgn.Game.from_board(b), file=pg, end="\n\n")
    cand.close(); opp.close()
    n = len(games)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=os.environ.get("BORG_SRC", ".")).stdout.strip() or "n/a"
    row = {"date": dt.date.today().isoformat(), "version": a.version, "git": sha, "candidate": a.candidate, "opponent": a.opponent,
           "games": n, "score": score, "score_pct": round(100 * score / n, 1) if n else 0, "illegal_moves": len(illegal),
           "book_rate": "" if book is None else round(book["rate"], 2), "perft_ok": perft_ok, "avg_plies": round(plies / n, 1) if n else 0,
           "seconds": round(time.time() - t0, 1)}
    row["verdict"] = "FAIL" if (illegal or not perft_ok or (book is not None and book["rate"] < 1.0)) else "PASS"
    detail.update(games=games, illegal=illegal, summary=row)
    (out / f"{a.version}-detail.json").write_text(json.dumps(detail, indent=1))
    csv_path = out / "results.csv"; new = not csv_path.exists()
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row)); new and w.writeheader(); w.writerow(row)
    print(json.dumps(row, indent=1))
    sys.exit(0 if row["verdict"] == "PASS" else 1)

if __name__ == "__main__":
    main()
