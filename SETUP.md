# Setup

Everything needed is in this repo now (the old `11cambrose/chess` fork is no longer required).

```bash
git clone https://github.com/11cambrose/coach-chad-chess-borg.git
cd coach-chad-chess-borg
uv venv --python 3.12 && . .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
chadborg think
```

Linux, macOS or Windows; Python 3.11+; no GPU, no Poetry, no torch.
For QA against Stockfish, download Stockfish 19 from the official release and pass `--stockfish PATH`.
