# Coach Chad's Chess Borg 🤖♟️

> **[TCZ]** Coach Chad vs Borg Chad — the unstoppable RL grind begins. Break their EGO. Steady growth. Rating thresholds. No illegal moves. Pure self-play. mmmbullseye COACH!!!

An AlphaZero-style reinforcement-learning chess agent, forked and rebranded for **The Chess Zone** (Coach Chad). The model learns purely from **self-play**, guided by **Monte Carlo Tree Search (MCTS)**, and is structurally incapable of selecting an **illegal move**.

**Ultimate goal:** Grow the Coach Chad bot engine so it achieves **consistent rating thresholds** with a **steady growth trajectory**. Hourly (or scheduled) iterations of Coach Chad vs Borg Chad produce stronger checkpoints over time.

## Architecture (unchanged core)

```
board (python-chess)
   │  encode_board  ─────────────▶ (19, 8, 8) tensor
   │
   ▼
ChessNet (ResNet tower)  ──▶  policy logits (4672)  +  value (tanh, [-1,1])
   │
   ▼
Evaluator: mask illegal moves, softmax over legal moves only
   │
   ▼
MCTS (PUCT selection, value back-ups)  ──▶  visit-count policy π  +  search value
   │
   ├─ self-play: sample move from π (temperature), store (state, π, result)
   ▼
Training: minimize  MSE(value, result) + cross-entropy(policy, π)
```

| Module | Responsibility |
| --- | --- |
| `encoding.py`  | board ↔ tensor, move ↔ index (4672 action space), **legal mask** |
| `network.py`   | residual policy + value network |
| `mcts.py`      | evaluator (legal masking) and PUCT Monte Carlo Tree Search |
| `selfplay.py`  | generate self-play games → training examples |
| `replay_buffer.py` | fixed-size example buffer |
| `train.py`     | one training pass (policy + value loss) |
| `agent.py`     | move-selection agent for play / evaluation |
| `cli.py`       | `loop`, `play`, `eval` commands |

## Coach Chad vs Borg Chad

- **Coach Chad** = the current improving network (`checkpoints/latest.pt` or newest `model_iter_N.pt`)
- **Borg Chad** = a previous checkpoint (or random baseline early on)

Use the `eval` command to pit them against each other and track win rates → approximate Elo growth.

```bash
# Evaluate Coach (model_a) vs Borg (model_b)
poetry run chesszero eval checkpoints/latest.pt --model-b checkpoints/model_iter_5.pt --games 20

# Or vs random (early baseline)
poetry run chesszero eval checkpoints/latest.pt --games 20
```

Rating tracking lives in `ratings/` (JSON log of match results + estimated Elo). See `scripts/track_ratings.py`.

## Training process (the RL loop)

Each *iteration*:

1. **Self-play (network frozen)**: generate games, store (state, π, z)
2. **Train**: update policy + value heads
3. **Checkpoint**: save `model_iter_N.pt` + `latest.pt`
4. **Optional match**: Coach vs Borg, log rating delta

```bash
# Small sanity run (CPU-friendly)
poetry run chesszero loop --iterations 2 --games 4 --simulations 40

# Resume + sample games for the viewer
poetry run chesszero loop --resume checkpoints/latest.pt --iterations 5 --games 10 --sample-games 5
```

## Hourly / scheduled pipeline

GitHub Actions workflow (`.github/workflows/rl-iteration.yml`) can be enabled for scheduled self-play + train + eval cycles.

**Note on compute:** Free GitHub-hosted runners are CPU-only and minute-limited. For real growth trajectory you need a self-hosted runner, GPU machine, or cloud (Colab, Lambda, etc.). The workflow is structured so you can point it at a larger runner or trigger manually via `workflow_dispatch`.

Alternatively, use the Grok Automations connector to schedule prompts that:

- Trigger a workflow_dispatch
- Analyze latest rating logs
- Report progress toward thresholds (e.g. 800 → 1200 → 1600 → 2000)

## Setup

Requires Python 3.11–3.14 and [Poetry](https://python-poetry.org/).

```bash
poetry install
```

## Usage summary

```bash
# Full RL loop
poetry run chesszero loop --iterations 10 --games 20 --simulations 100

# Play human vs Coach Chad
poetry run chesszero play checkpoints/latest.pt --color white

# Coach vs Borg evaluation
poetry run chesszero eval checkpoints/latest.pt --model-b checkpoints/model_iter_3.pt --games 30

# Viewer for sampled self-play games
poetry run chesszero viewer
```

## Rating growth targets (Coach Chad style)

| Threshold | Meaning |
|-----------|---------|
| 800       | Beats random consistently |
| 1200      | Solid club beginner |
| 1600      | Intermediate, starts finding tactics |
| 2000      | Strong amateur / candidate master trajectory |
| 2200+     | Borg-level pressure cooking |

Track steady upward slope in `ratings/history.json`. No plateaus allowed. Break the EGO of the previous version every iteration.

## Tests

```bash
poetry run pytest
```

## Origin

Forked from [albrodfer1/chess](https://github.com/albrodfer1/chess) (ChessZero / AlphaZero-style). Rebranded and extended for Coach Chad's Chess Borg at The Chess Zone.

**Disclaimer:** Core code & original docs are AI-generated. The Borg grind is real.

---

*Schedule a consultation with Coach Chad today & learn how The Chess Zone can unlock a new routine of daily mental fitness!! Log on Anon and grind for interesting tactics!*

Chef’s kiss – xoxo – COACH Chad!!!
