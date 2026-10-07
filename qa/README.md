# chadborg QA

| file | what |
| --- | --- |
| `chadborg_qa.py` | g5/book rates, legality on every move, mate-assist suite, Fly best_pick/regret, games vs random and Stockfish. `--quick` (CI) or `--full`. `--history ratings/history.json` appends a summary. |
| `borg_qa.py` | engine-agnostic harness (perft sanity, legality, `--expect-black-first`, 12-opening suite, regression match). Adapters: `random`, `chadborg:<profile>[:depth]`, `think:<profile>@<url>`, `uci:<path>[:depth]`, `chesszero:<ckpt>`. |
| `build_heldout.py` | builds `data/heldout-sf19-d10.jsonl`: 249 positions sampled deterministically (plies 8–80, every 4th) from 25 Coach Chad house games, with a Stockfish 19 depth-10 score for **every** legal move. |
| `build_mate_suite.py` | builds `data/mate-suite.jsonl`: 18 "take the mate" + 77 "don't walk into mate in 1" positions (hand-written + mined from house PGNs), verified with python-chess. |

## Fly metrics

- **best_pick**: share of positions where the engine's move has Stockfish's best score.
- **regret** (win-probability units): `wp(best) - wp(chosen)`, `wp(cp) = 1/(1+10^(-cp/400))`.
- **random baseline** is exact (expectation over every legal move), not sampled.
- **closer_than_random** = `1 - regret / regret_random` (Fly reports 67%).

The held-out games must stay out of any training data. Self-play labels in
`ratings/rl_buffer.jsonl` currently share no positions with the held-out set.

Expected book rates: lite 1...g5 = 100%. macos 1...g5 ≈ 80.5% and 1...c5 ≈ 10.5%,
because the 10% "random legal" branch can also land on g5 or c5 (1 in 20 each).
