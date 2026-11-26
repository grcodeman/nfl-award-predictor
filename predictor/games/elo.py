"""games-elo: Elo ratings from every game since 1999, with a margin-of-victory multiplier.

Every team starts at 1500 in 1999 (the Texans at 1500 in 2002), and before each season every rating is
pulled part of the way back to 1500. For a game, d = home rating + home edge - away rating, with no home
edge at a neutral site. The home team's win probability is 1 / (1 + 10^(-d/400)) and its predicted
margin d / 25 points. After the game both ratings move by K x multiplier x (result - probability), with
result 1, 0.5 or 0 for the home team. The multiplier, ln(|margin| + 1) x 2.2 / (0.001 x the winner's
rating edge + 2.2), grows with the margin but less for a favorite, so a team can't climb on blowouts of
weak teams alone. That is FiveThirtyEight's NFL Elo, without its travel and quarterback adjustments.

The parameters were picked on 2002-2014 games only (lowest log loss on a small grid, PARAMS below) and
then frozen; 2015 onward is the backtest (predictor/games/backtest.py).
"""
import math

import pandas as pd

from predictor.data import OLD_TEAM_CODES

MEAN = 1500
# Picked on 2002-2014 by log loss over K 10-30, home edge 35-75 and offseason pull 0.25-0.6.
PARAMS = {"k": 20, "home_edge": 55, "regress": 0.45}


def run(games, k=PARAMS["k"], home_edge=PARAMS["home_edge"], regress=PARAMS["regress"]):
    """Pre-game ratings and predictions for every game in `games` (rows from load_schedules, any seasons,
    played or not), in kickoff order. Ratings move only after a played game, so each game's numbers use
    only the games before it, and a game not played yet sees today's ratings."""
    g = games.sort_values(["season", "kickoff", "game_id"])
    ratings, season, rows = {}, None, []
    for r in g.itertuples():
        if r.season != season:  # new season: pull everyone back toward the mean
            ratings = {t: MEAN + (1 - regress) * (x - MEAN) for t, x in ratings.items()}
            season = r.season
        home, away = OLD_TEAM_CODES.get(r.home_team, r.home_team), OLD_TEAM_CODES.get(r.away_team, r.away_team)
        h, a = ratings.setdefault(home, MEAN), ratings.setdefault(away, MEAN)
        d = h + (0 if r.location == "Neutral" else home_edge) - a
        p = 1 / (1 + 10 ** (-d / 400))
        rows.append((r.game_id, h, a, p, d / 25))
        if pd.notna(r.result):
            margin = r.result
            actual = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
            winner_edge = d if margin > 0 else -d if margin < 0 else 0.0
            mult = math.log(abs(margin) + 1) * 2.2 / (0.001 * winner_edge + 2.2) if margin else math.log(2)
            shift = k * mult * (actual - p)
            ratings[home], ratings[away] = h + shift, a - shift
    out = pd.DataFrame(rows, columns=["game_id", "home_elo", "away_elo", "home_win_prob", "home_margin"])
    return games[["game_id"]].merge(out, on="game_id", how="left")


def predict(games):
    """The ledger interface every game model has: game_id, home_win_prob, home_margin, plus any inputs
    worth showing (here the two ratings)."""
    p = run(games)
    inputs = [{"home_elo": int(round(h)), "away_elo": int(round(a))} for h, a in zip(p.home_elo, p.away_elo)]
    return p.assign(inputs=inputs)
