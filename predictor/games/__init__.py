"""Game picks: every model's win probability and margin for each game, written to the ledger before
kickoff and graded against the result and the betting market (ledger.py).

MODELS maps a model's name to its predict(games) function, which takes every game from load_schedules
(1999 on, played or not) and returns, for each game_id, home_win_prob, home_margin and a dict of inputs
worth showing. It may use any game's result, so it must only let a game's numbers depend on games
kicked off before it; backtest.py replays history on the same function. Names and versions are in
predictor/models.py.
"""
from predictor.games import elo

MODELS = {"games-elo": elo.predict}
CHAMPION = "games-elo"  # feeds the dashboard; the rest are challengers
