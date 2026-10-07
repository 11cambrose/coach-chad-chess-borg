#!/usr/bin/env python3
"""chadborg QA: book rates, legality, mate assists, Fly metrics, Stockfish games.

  python qa/chadborg_qa.py --quick                     # CI: no Stockfish needed, ~1 min
  python qa/chadborg_qa.py --full --stockfish PATH     # everything, incl. games vs SF

Fly metrics use qa/data/heldout-sf19-d10.jsonl (Stockfish 19 depth-10 score for every
legal move of 249 positions from Coach Chad house PGNs). Regret is in win-probability
units: wp(cp) = 1 / (1 + 10^(-cp/400)); regret = wp(best) - wp(chosen). The random
baseline is exact (expectation over all legal moves), not sampled.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import random
import subprocess
import sys
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn

import chadborg
from chadborg.engine import choose_move

HERE = Path(__file__).resolve().parent
HELDOUT = HERE / "data" / "heldout-sf19-d10.jsonl"
MATES = HERE / "data" / "mate-suite.jsonl"
SUITE = {
    "startpos": [],
    "borg-vs-e4": ["e4", "g5"], "borg-vs-d4": ["d4", "g5"], "borg-vs-c4": ["c4", "g5"],
    "borg-vs-Nf3": ["Nf3", "g5"], "borg-vs-f4": ["f4", "g5"], "borg-Bxg5-line": ["d4", "g5", "Bxg5"],
    "borg-e4-d4-h6": ["e4", "g5", "d4", "h6"], "borg-e4-d4-Bg7": ["e4", "g5", "d4", "Bg7"],
    "kings-gambit": ["e4", "e5", "f4"], "sicilian": ["e4", "c5"], "old-benoni": ["d4", "c5"], "french": ["e4", "e6"],
}


class IllegalMove(AssertionError):
    pass


class Borg:
    def __init__(self, spec: str, seed: int = 0):
        profile, _, depth = spec.partition(":")
        self.profile, self.depth = profile, (int(depth) if depth else None)
        self.name = f"chadborg-{chadborg.__version__}:{spec}"
        self.rng = random.Random(seed)
        self.moves_checked = 0

    def think(self, board: chess.Board):
        t = choose_move(board.copy(), rng=self.rng, profile=self.profile, depth=self.depth)
        self.moves_checked += 1
        if t.choice not in board.legal_moves:
            raise IllegalMove(f"{self.name} played {t.choice} in {board.fen()}")
        return t

    def choose(self, board: chess.Board) -> chess.Move:
        return self.think(board).choice


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if n == 0:
        return [0.0, 0.0]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


def wp(cp: float) -> float:
    return 1.0 / (1.0 + 10 ** (-cp / 400.0))


# ---------------------------------------------------------------- book rates
def book_rates(samples_per_first: int, seed: int) -> dict:
    firsts = [m for m in chess.Board().legal_moves]
    out = {}
    # lite: Black's reply to every White first move must be ...g5
    hits = n = 0
    for i, w in enumerate(firsts):
        for s in range(max(3, samples_per_first // 10)):
            b = chess.Board(); b.push(w)
            borg = Borg("lite", seed + 1000 * i + s)
            hits += borg.choose(b) == chess.Move.from_uci("g7g5"); n += 1
    out["lite_black_g5"] = {"hits": hits, "n": n, "rate": round(hits / n, 4), "ci95": wilson(hits, n), "expect": 1.0}
    # macos: 80% g5 / 10% c5 / 10% random legal (which can also land on g5/c5)
    g5 = c5 = n = 0
    for i, w in enumerate(firsts):
        for s in range(samples_per_first):
            b = chess.Board(); b.push(w)
            m = Borg("macos", seed + 7000 + 1000 * i + s).choose(b)
            g5 += m.uci() == "g7g5"; c5 += m.uci() == "c7c5"; n += 1
    out["macos_black_g5"] = {"hits": g5, "n": n, "rate": round(g5 / n, 4), "ci95": wilson(g5, n), "expect": 0.80 + 0.10 / 20}
    out["macos_black_c5"] = {"hits": c5, "n": n, "rate": round(c5 / n, 4), "ci95": wilson(c5, n), "expect": 0.10 + 0.10 / 20}
    # macos White steer: 1.e4 (95%) and 2.f4 after 1.e4 e5 (95%)
    k = n2 = f4 = 0
    total = samples_per_first * 4
    for s in range(total):
        k += Borg("macos", seed + 50_000 + s).choose(chess.Board()).uci() == "e2e4"
        b = chess.Board(); b.push_san("e4"); b.push_san("e5")
        f4 += Borg("macos", seed + 90_000 + s).choose(b).uci() == "f2f4"; n2 += 1
    out["macos_white_e4"] = {"hits": k, "n": total, "rate": round(k / total, 4), "ci95": wilson(k, total), "expect": 0.95}
    out["macos_white_f4"] = {"hits": f4, "n": n2, "rate": round(f4 / n2, 4), "ci95": wilson(f4, n2), "expect": 0.95}
    return out


# ---------------------------------------------------------------- mate assists
def mate_suite(spec: str, seed: int) -> dict:
    rows = [json.loads(line) for line in MATES.read_text().splitlines() if line.strip()]
    res = {"take": [0, 0], "avoid": [0, 0], "fails": []}
    borg = Borg(spec, seed)
    for r in rows:
        b = chess.Board(r["fen"])
        m = borg.choose(b).uci()
        ok = m in r["mates"] if r["kind"] == "take" else m not in r["losing"]
        res[r["kind"]][0] += ok; res[r["kind"]][1] += 1
        if not ok:
            res["fails"].append({"kind": r["kind"], "fen": r["fen"], "played": m, "src": r["src"]})
    return res


# ---------------------------------------------------------------- Fly metrics
def fly_metrics(spec: str, seed: int, limit: int | None = None) -> dict:
    rows = [json.loads(line) for line in HELDOUT.read_text().splitlines() if line.strip()]
    if limit:
        rows = rows[:limit]
    borg = Borg(spec, seed)
    e_best = e_reg = e_cp = r_best = r_reg = r_cp = 0.0
    t0 = time.time()
    for r in rows:
        sc = r["scores_cp"]
        best = max(sc.values())
        b = chess.Board(r["fen"])
        m = borg.choose(b).uci()
        e_best += sc[m] == best
        e_reg += wp(best) - wp(sc[m])
        e_cp += min(best - sc[m], 1000)
        vals = list(sc.values())
        r_best += sum(v == best for v in vals) / len(vals)
        r_reg += sum(wp(best) - wp(v) for v in vals) / len(vals)
        r_cp += sum(min(best - v, 1000) for v in vals) / len(vals)
    n = len(rows)
    out = {
        "positions": n,
        "best_pick": round(e_best / n, 4), "best_pick_random": round(r_best / n, 4),
        "regret_wp": round(e_reg / n, 4), "regret_wp_random": round(r_reg / n, 4),
        "regret_cp_capped": round(e_cp / n, 1), "regret_cp_capped_random": round(r_cp / n, 1),
        "seconds": round(time.time() - t0, 1),
    }
    out["closer_than_random"] = round(1 - out["regret_wp"] / out["regret_wp_random"], 4)
    return out


# ---------------------------------------------------------------- games
def play(cand, opp, start, cand_white, max_plies=200):
    b = chess.Board()
    for s in start:
        b.push_san(s)
    while not b.is_game_over(claim_draw=True) and b.ply() < max_plies:
        mover = cand if (b.turn == chess.WHITE) == cand_white else opp
        m = mover.choose(b)
        if m not in b.legal_moves:
            raise IllegalMove(f"{getattr(mover, 'name', mover)} played {m} in {b.fen()}")
        b.push(m)
    res = b.result(claim_draw=True)
    s = 0.5 if res in ("*", "1/2-1/2") else (1.0 if res == "1-0" else 0.0)
    return (s if cand_white else 1 - s), b, res


class RandomMover:
    def __init__(self, seed):
        self.r = random.Random(seed); self.name = "random"

    def choose(self, b):
        return self.r.choice(list(b.legal_moves))


class SF:
    def __init__(self, path, depth):
        self.e = chess.engine.SimpleEngine.popen_uci(path)
        self.e.configure({"Threads": 1, "Hash": 16})
        self.depth = depth; self.name = f"{self.e.id.get('name', 'stockfish')} d{depth}"

    def choose(self, b):
        return self.e.play(b, chess.engine.Limit(depth=self.depth)).move

    def close(self):
        self.e.quit()


def match(spec, opp, openings, seed, pgn_fh=None, max_plies=200):
    borg = Borg(spec, seed)
    w = d = l = 0
    games = []
    for name in openings:
        for cw in (True, False):
            s, b, res = play(borg, opp, SUITE[name], cw, max_plies)
            w += s == 1.0; d += s == 0.5; l += s == 0.0
            games.append({"opening": name, "borg_white": cw, "result": res, "score": s, "plies": b.ply()})
            if pgn_fh:
                g = chess.pgn.Game.from_board(b)
                g.headers.update({"Event": f"chadborg QA {name}", "White": borg.name if cw else opp.name,
                                  "Black": opp.name if cw else borg.name, "Result": res})
                print(g, file=pgn_fh, end="\n\n")
    n = w + d + l
    return {"opponent": opp.name, "games": n, "wins": w, "draws": d, "losses": l,
            "score": round((w + 0.5 * d) / n, 4), "borg_moves_checked": borg.moves_checked, "detail": games}


def git_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=HERE).stdout.strip() or "n/a"
    except OSError:
        return "n/a"


def main() -> int:
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    ap.add_argument("--engines", default=None, help="comma list, e.g. lite,macos:2 (macos:1 == lite after the book)")
    ap.add_argument("--stockfish", default=os.environ.get("STOCKFISH"))
    ap.add_argument("--sf-depth", type=int, default=1)
    ap.add_argument("--sf-engines", default=None, help="engines that play SF (default lite,macos:2 full)")
    ap.add_argument("--seed", type=int, default=20261006)
    ap.add_argument("--out-dir", default="qa-results")
    ap.add_argument("--label", default=None)
    ap.add_argument("--sections", default="book,mates,fly,random,sf", help="subset of book,mates,fly,random,sf")
    ap.add_argument("--fly-limit", type=int, default=None, help="only the first N held-out positions")
    ap.add_argument("--history", default=None, help="append summary to this JSON list (ratings/history.json)")
    a = ap.parse_args()
    quick = not a.full
    sections = set(a.sections.split(","))
    engines = (a.engines or ("lite" if quick else "lite,macos:2")).split(",")
    sf_engines = (a.sf_engines or ("lite" if quick else "lite,macos:2")).split(",")
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    label = a.label or f"chadborg-{chadborg.__version__}"
    t0 = time.time()
    report = {"label": label, "version": chadborg.__version__, "git": git_sha(), "mode": "quick" if quick else "full",
              "ran_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "seed": a.seed}
    illegal: list[str] = []
    try:
        if "book" in sections:
            report["book"] = book_rates(40 if quick else 150, a.seed)
        if "mates" in sections:
            report["mate_assists"] = {e: mate_suite(e, a.seed) for e in engines}
        if "fly" in sections:
            report["fly"] = {e: fly_metrics(e, a.seed, a.fly_limit) for e in engines}
        rnd = {}
        for e in (engines if "random" in sections else []):
            nopen = ["startpos", "borg-vs-e4", "kings-gambit"] if quick else list(SUITE)
            if e.endswith(":2") or e.endswith(":3"):
                nopen = nopen[:4]
            rnd[e] = match(e, RandomMover(a.seed), nopen, a.seed)
        if rnd:
            report["vs_random"] = {e: {k: v for k, v in r.items() if k != "detail"} for e, r in rnd.items()}
        if a.stockfish and "sf" in sections:
            sf = SF(a.stockfish, a.sf_depth)
            report["vs_stockfish"] = {}
            with open(out / f"{label}-vs-sf-d{a.sf_depth}.pgn", "w") as fh:
                for e in sf_engines:
                    report["vs_stockfish"][e] = match(e, sf, ["startpos", "borg-vs-e4", "kings-gambit"] if quick else list(SUITE), a.seed, fh)
            sf.close()
    except IllegalMove as exc:
        illegal.append(str(exc))
    report["illegal_moves"] = illegal
    report["seconds"] = round(time.time() - t0, 1)
    (out / f"{label}-{report['mode']}.json").write_text(json.dumps(report, indent=1))

    rows = []
    for e in engines:
        f = report.get("fly", {}).get(e, {})
        m = report.get("mate_assists", {}).get(e, {})
        vs = report.get("vs_stockfish", {}).get(e, {})
        vr = report.get("vs_random", {}).get(e, {})
        bk = report.get("book", {})
        g5 = bk.get("lite_black_g5" if e == "lite" else "macos_black_g5", {})
        rows.append({
            "date": dt.date.today().isoformat(), "label": label, "git": report["git"], "engine": e, "mode": report["mode"],
            "g5_rate": g5.get("rate", ""), "g5_n": g5.get("n", ""), "illegal_moves": len(illegal),
            "mate_take": "{}/{}".format(*m["take"]) if m else "", "mate_avoid": "{}/{}".format(*m["avoid"]) if m else "",
            "best_pick": f.get("best_pick", ""), "best_pick_random": f.get("best_pick_random", ""),
            "regret_wp": f.get("regret_wp", ""), "regret_wp_random": f.get("regret_wp_random", ""),
            "closer_than_random": f.get("closer_than_random", ""),
            "vs_random": f"{vr.get('wins','')}-{vr.get('draws','')}-{vr.get('losses','')}" if vr else "",
            "vs_sf": f"{vs.get('wins')}-{vs.get('draws')}-{vs.get('losses')} ({vs.get('opponent')})" if vs else "",
        })
    csv_path = out / "results.csv"
    new = not csv_path.exists()
    with open(csv_path, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        if new:
            w.writeheader()
        w.writerows(rows)
    if a.history:
        hp = Path(a.history)
        hist = json.loads(hp.read_text()) if hp.exists() and hp.read_text().strip() else []
        hist.append({"kind": "qa", "ran_at": report["ran_at"], "label": label, "git": report["git"],
                     "mode": report["mode"], "rows": rows})
        hp.write_text(json.dumps(hist, indent=2) + "\n")

    print(json.dumps(rows, indent=1))
    bad = list(illegal)
    if "book" in report and report["book"]["lite_black_g5"]["rate"] != 1.0:
        bad.append("lite g5 rate != 100%")
    for e, m in report.get("mate_assists", {}).items():
        if m["take"][0] != m["take"][1] or m["avoid"][0] != m["avoid"][1]:
            bad.append(f"mate assists failed for {e}")
    for e, f in report.get("fly", {}).items():
        if f["regret_wp"] >= f["regret_wp_random"]:
            bad.append(f"{e} not closer to best than random")
    print("VERDICT:", "FAIL " + "; ".join(bad) if bad else "PASS", f"({report['seconds']}s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
