"""Coach Chad Borg — lite /think and macos beast search."""

from .engine import ThinkResult, choose_move, match_score, play_game, rank_moves
from .openings import PROFILES
from .server import think_payload

__all__ = [
    "choose_move",
    "rank_moves",
    "play_game",
    "match_score",
    "ThinkResult",
    "think_payload",
    "PROFILES",
]
__version__ = "0.4.0"
