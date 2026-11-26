"""Game picks, the weekly run and the backtest.

python -m predictor.games            grade every picked game that has finished, update the scoreboard, then
                                     write the next week's picks if they're due (the weekly run)
python -m predictor.games backtest   rewrite each model's 2015-2025 backtest

The weekly run writes a week's picks once the week before it is final and the week's first game is
less than six days out (ledger.PICK_WINDOW): on the Tuesday morning run for a Thursday opener, and the
Monday after week 18 for the Wild Card round. It never writes a week that has kicked off or already has
a file, so rerunning it is safe.
"""
import argparse
import json

import nflreadpy as nfl
import pandas as pd

from predictor.data import ROOT, load_schedules
from predictor.games import MODELS
from predictor.games.backtest import backtest
from predictor.games.ledger import grade, next_week, picks_path, write_index, write_picks, write_scoreboard
from predictor.models import version

FIRST_SEASON = 1999  # the ratings start here


def schedule():
    """Every game from 1999 through next season, if it's on the schedule yet."""
    return load_schedules(range(FIRST_SEASON, nfl.get_current_season() + 2))


def weekly():
    now = pd.Timestamp.now(tz="UTC")
    games = schedule()
    for path in grade(games, now):
        print(f"graded {path.relative_to(ROOT)}")
    if write_scoreboard(now):
        print("updated predictions/games/scoreboard.json")
    target, why = next_week(games, now)
    if target is None:
        print(f"no picks to write: {why}")
    elif picks_path(*target).exists():
        print(f"{target[0]} week {target[1]} picks are already in {picks_path(*target).relative_to(ROOT)}")
    else:
        show_picks(games, write_picks(games, *target, now))
    write_index()


def show_picks(games, path):
    print(f"wrote {path.relative_to(ROOT)}")
    picks = json.loads(path.read_text())
    wk = games[(games["season"] == picks["season"]) & (games["week"] == picks["week"])].set_index("game_id")
    for p in picks["picks"]:
        g = wk.loc[p["game_id"]]
        line = "no line" if pd.isna(g.spread_line) else f"market {g.home_team} {-g.spread_line:+g}"
        print(f"  {p['model']} {p['version']}  {g.away_team:>3} at {g.home_team:<3}"
              f"  home {p['home_win_prob']:.0%}, by {p['home_margin']:+.1f}  ({line})")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=["weekly", "backtest"], default="weekly")
    args = parser.parse_args()
    if args.command == "backtest":
        games = schedule()
        for name in MODELS:
            path, totals = backtest(games, name)
            print(f"{name} {version(name)} -> {path.relative_to(ROOT)}")
            for t in totals:
                print(f"  {t['scorer']:<10} {t['correct'] / t['games']:.1%} of {t['games']},"
                      f" log loss {t['log_loss']:.3f}, Brier {t['brier']:.3f}, margin miss {t['margin_error']:.1f}")
    else:
        weekly()


if __name__ == "__main__":
    main()
