# Coach Chad's Chess Borg 🤖♟️

> **[TCZ]** Coach Chad vs Borg Chad. Legal moves only. CPU only. No illegal moves, ever.

`chadborg` is a Fly-style chess engine (see [REDESIGN.md](REDESIGN.md)):

1. enumerate **legal moves only** (python-chess),
2. play each one out and score the resulting board (1-ply feature ranker),
3. pick the best,
4. two hard assists: **take a mate in 1** when one exists, and **never walk into mate in 1**.

Two personalities:

| profile | what it does |
| --- | --- |
| `lite` | 1-ply ranker. As Black, its first reply is **always 1...g5** when legal. Cheap enough for a `POST /think` box. |
| `macos` | alpha-beta + capture/check quiescence (default depth 3). As White it steers the King's Gambit (1.e4 95%, 2.f4 95%). As Black its first reply is 80% 1...g5, 10% 1...c5, 10% random legal. |

Black never moves first; the book fires only on Black's first reply.

## Install (uv or pip, no Poetry, no torch)

```bash
uv venv --python 3.12 && . .venv/bin/activate
uv pip install -e ".[dev]"          # or: python -m pip install -e ".[dev]"
pytest -q
```

## Use

```bash
chadborg think                                  # lite from the start position
chadborg think --profile macos --depth 2 --fen "<FEN>"
chadborg play --color white --profile lite      # human vs Borg in the terminal
chadborg serve --host 127.0.0.1 --port 8787     # POST /think {"fen","profile","depth"}
chadborg rl --profile macos --games 2 --depth 2 # self-play labels -> ratings/rl_buffer.jsonl
```

`POST /think` validates input: body must be a JSON object, `profile` in `lite|macos|default`,
`depth` an integer 1–3. Bad input gets a 400 JSON error.

## QA

```bash
python qa/chadborg_qa.py --quick                          # CI gate, ~1–2 min
python qa/chadborg_qa.py --full --stockfish /path/to/sf   # adds macos d2, all openings, games vs Stockfish
python qa/borg_qa.py --candidate chadborg:lite --version X --opponent uci:/path/to/sf:1 --expect-black-first g7g5
```

Metrics: 1...g5 rate, illegal moves (hard fail), mate-assist suite (take / avoid), Fly
**best_pick** and **regret vs random** on 249 held-out positions from Coach Chad house games
scored by Stockfish 19, and games vs random / Stockfish at fixed depth. See [qa/README.md](qa/README.md).

## Workflows

- `PR QA` (`.github/workflows/pr-qa.yml`): pytest on 3.11/3.12 + quick QA on every pull request.
- `Coach Chad RL Iteration` (`.github/workflows/rl-iteration.yml`): install, pytest, short macos
  self-play, QA metrics appended to `ratings/history.json` (uploaded as an artifact).
  **Disabled on GitHub (paused 2026-10-06).** Re-enable from the Actions tab only when wanted.

## Layout

```
src/chadborg/   eval, engine, openings, search, server, rl, cli
tests/          pytest
qa/             chadborg_qa.py, borg_qa.py, held-out + mate-suite data and builders
web/            layout sketch for a /think front end
ratings/        history.json (QA metrics), rl_buffer.jsonl (self-play labels)
```

The old AlphaZero/Poetry/torch path (`chesszero`, `11cambrose/chess`) is retired as the default.
