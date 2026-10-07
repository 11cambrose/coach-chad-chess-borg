# Coach Chad Borg redesign — 2026-09-11

Source of truth for the functional system:
https://x.com/ernestosoftware/status/2098449947083362527
https://flychess-hq.vercel.app/
https://flychess-production.up.railway.app/api/info

## What the fly actually does (not marketing)

Live API (`/api/info`): 164,587 neurons, 25,563,197 synapses, 8,865 sensory, 2,129 motor, `trained=true`, mode=`choice`.
Held-out metrics: best_pick 0.407 vs random 0.087, regret 0.062 vs 0.189, n_turns=844, steps=30.

UI copy, verified on the site:

> Every legal move is played out and the connectome is simulated on the position it would create. Each board is injected as current into 8,865 sensory neurons; 2,129 descending and motor neurons are read out, and a trained map ranks those options against each other. The fly plays the one it scores highest. On held-out positions its pick is 67% closer to the best available move than choosing at random. Two assists sit outside the fly: it takes a mate when one is there, and it will not walk into mate in one.

That is **1-ply legal-move ranking + two tactical hard rules**. It is not AlphaZero, not MCTS-100, not a 128-filter ResNet, not Poetry-on-macOS.

`martialsystems/fly_chess` is a *different* closed science repo (LIF graph shuffle test, wiring does **not** pick the move). Do not treat that negative-result paper as the playable app.

## Why the previous Borg was rekt

- Engine required PyTorch + Poetry + checkpoint files the orchestration repo never shipped.
- GitHub Actions on free CPU cannot run AlphaZero self-play in 90 minutes.
- Split repos: `11cambrose/coach-chad-chess-borg` had workflow/README only; playable source stayed on `11cambrose/chess`.
- macOS Homebrew `/opt/homebrew/bin/python3.12` assumptions (Fly research scripts do this; we copied the wrong stack).
- Elo was invented from 4 noisy eval games against random.

## Current stack (v0.4.0)

```
src/chadborg/
  eval.py       feature ranker
  engine.py     choose_move(profile, depth) + mate assists
  openings.py   lite always 1...g5 reply; macos KG + 80/10/10 first reply
  search.py     macos alpha-beta + quiescence
  server.py     POST /think  (mobile/Railway contract)
  rl.py         self-play → ratings/rl_buffer.jsonl
  cli.py        think | play | serve | rl | eval
tests/test_engine.py         11 original tests
tests/test_fixes_0_4_1.py    regression tests for the two bugs fixed in QA (2026-10-06)
qa/                          chadborg_qa.py (Fly metrics, mate suite, book rates, SF games), borg_qa.py
web/index.html               layout sketch only
```

Black never moves first. Mix/g5 fire only at ply==1 (Black's first reply).

## Next phase (parked)

1. User test cases (PGN/FEN suite) drop into `tests/`.
2. Linear head on PGN + `rl_buffer.jsonl`.
3. Mobile wrap: same `think_payload(fen, profile)` / `POST /think` JSON. No new engine.

Run (Linux/macOS/Windows, no Poetry, no GPU):

```
uv venv --python 3.12 && . .venv/bin/activate
uv pip install -e ".[dev]"
chadborg think
chadborg eval --games 20
chadborg play --color white
pytest -q
python qa/chadborg_qa.py --quick
```

Smoke (2026-09-11): start position picks e4/d4; 12–0 vs random legal in 12 games; tests 5/5.

## QA pass 2026-10-06 (upload `chadborg-upload-2026-10-06`)

Two clear bugs fixed, each with regression tests (`tests/test_fixes_0_4_1.py`):

1. **Quiescence ignored the side to move.** `_quiesce` always maximized for the root side, so at
   the opponent's nodes it never considered the opponent's captures (it stood pat or picked the
   capture best for *us*). Example: after 1.e4 e5 2.Nf3 Nc6, macos depth 3 played 3.Nxe5?
   (scored +393) because it never saw ...Nxe5. Now minimax-consistent (value from White ==
   −value from Black); macos picks 3.Nc3 and the search is ~2x faster.
2. **`POST /think` dropped the connection on valid JSON with wrong types** (`{"depth":"3"}`,
   `{"profile":7}`, `[1,2]` raised AttributeError/TypeError in the handler; only ValueError was
   caught) and `depth` was uncapped. Now: body must be an object, `fen` a string, `profile` one
   of `default|lite|macos`, `depth` an int 1–3 (else 400 JSON); illegal positions → 400;
   oversized bodies → 413; any other failure → 500 JSON instead of a dropped socket.

Known, not changed (design calls for the owner):

- `chadborg eval` still writes `est_elo_vs_random400` to `ratings/history.json`, which is the
  "Elo from games vs random" this doc says not to claim. The workflows use `qa/chadborg_qa.py`
  (Fly metrics) instead.
- `test_refuses_walk_into_mate` cannot fail (the position has no mate-in-1 trap);
  `test_refuses_back_rank_trap` covers the assist properly.
- macos depth 3 costs ~10–17 s/move on one CPU core; QA games use depth 2.

## Growth path that does not require a Mac

1. Keep the Fly loop forever (legal mask + 1-ply + mate assists).
2. Replace `eval.py` features with a linear head trained on Coach Chad PGN (11brose / tksatxchad_ambrose / lichess TCZ_CoachChad) — supervised, CPU.
3. Optional 2–3 ply only on checks/captures (same as “steps=30” budget on Railway).
4. Host the think API on Railway/Fly.io like they did. Frontend on Vercel. No macOS in the path.
5. Report Fly-style metrics (best_pick vs random, regret) before claiming Elo.
