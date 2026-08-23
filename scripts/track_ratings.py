#!/usr/bin/env python3
"""Append Coach vs Borg match results to ratings/history.json and estimate Elo.

Simple Elo model: K=32, starting 1000 for random, +delta based on score.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

RATINGS_DIR = Path("ratings")
HISTORY = RATINGS_DIR / "history.json"
LAST_MATCH = RATINGS_DIR / "last_match.txt"


def expected_score(ra: float, rb: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))


def update_elo(ra: float, rb: float, score_a: float, k: float = 32.0) -> tuple[float, float]:
    ea = expected_score(ra, rb)
    eb = 1.0 - ea
    return ra + k * (score_a - ea), rb + k * ((1.0 - score_a) - eb)


def parse_last_match(text: str) -> dict | None:
    # Looks for: model_a wins: X | model_b wins: Y | draws: Z
    # or random
    m = re.search(
        r"model_a wins:\s*(\d+)\s*\|\s*(\w+)\s*wins:\s*(\d+)\s*\|\s*draws:\s*(\d+)",
        text,
        re.I,
    )
    if not m:
        return None
    wins_a, label_b, wins_b, draws = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
    total = wins_a + wins_b + draws
    if total == 0:
        return None
    score_a = (wins_a + 0.5 * draws) / total
    return {
        "wins_a": wins_a,
        "wins_b": wins_b,
        "draws": draws,
        "total": total,
        "score_a": score_a,
        "opponent": label_b,
    }


def main() -> None:
    RATINGS_DIR.mkdir(parents=True, exist_ok=True)
    history = []
    if HISTORY.exists():
        history = json.loads(HISTORY.read_text())

    coach_elo = history[-1]["coach_elo"] if history else 1000.0
    borg_elo = history[-1].get("borg_elo", 800.0) if history else 800.0

    result = None
    if LAST_MATCH.exists():
        result = parse_last_match(LAST_MATCH.read_text())

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "coach_elo": coach_elo,
        "borg_elo": borg_elo,
    }

    if result:
        score = result["score_a"]
        new_coach, new_borg = update_elo(coach_elo, borg_elo, score)
        entry.update(
            {
                "match": result,
                "coach_elo": round(new_coach, 1),
                "borg_elo": round(new_borg, 1),
                "delta": round(new_coach - coach_elo, 1),
            }
        )
        print(f"Coach Chad Elo: {coach_elo:.1f} → {new_coach:.1f} (Δ {new_coach - coach_elo:+.1f})")
        print(f"Borg Chad Elo:  {borg_elo:.1f} → {new_borg:.1f}")
        print(f"Match: {result['wins_a']}-{result['wins_b']}-{result['draws']} vs {result['opponent']}")
    else:
        print("No parseable last_match.txt — logging current Elo only")

    history.append(entry)
    HISTORY.write_text(json.dumps(history, indent=2))
    print(f"Wrote {HISTORY}")


if __name__ == "__main__":
    main()
