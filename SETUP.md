# Full source setup

The orchestration layer (README, workflow, ratings tracker) lives in this repo.

The complete ChessZero source (src/, tests/, docs/, etc.) is in the companion fork:

https://github.com/11cambrose/chess

## Quick local setup

```bash
git clone https://github.com/11cambrose/chess.git coach-chad-src
cd coach-chad-src
# optionally overlay the borg workflow & scripts
cp -r ../coach-chad-chess-borg/.github .
cp -r ../coach-chad-chess-borg/scripts .
cp -r ../coach-chad-chess-borg/ratings .
# or just work from the chess fork and copy the workflow there

poetry install
poetry run chesszero loop --iterations 1 --games 2 --simulations 20
```

For the scheduled pipeline, enable Actions on this repo and/or the fork, and attach a self-hosted GPU runner for real strength growth.
