"""Loaders shared by the award and game models: the nflverse download cache, team codes, the schedule
(every game with its score, closing line and starting QBs) and each team's record through any week."""
from pathlib import Path

import nflreadpy as nfl
import pandas as pd
from nflreadpy.config import update_config

ROOT = Path(__file__).resolve().parent.parent

# Keep nflreadpy downloads on disk in the gitignored .cache/ folder; it re-downloads at most once a day.
update_config(cache_mode="filesystem", cache_dir=ROOT / ".cache" / "nflreadpy", verbose=False)

# Schedules use the team code of the time; stats use today's code for every season.
OLD_TEAM_CODES = {"STL": "LA", "SD": "LAC", "OAK": "LV"}


def load_schedules(seasons):
    """Every game of `seasons`, regular season and playoffs, as nflverse lists it: team codes of the time,
    `result` = home score minus away score (blank until played), `spread_line` = points the home team
    is favored by."""
    return nfl.load_schedules(list(seasons)).to_pandas()


def load_team_records(seasons, through_week):
    """team_games, team_win_pct, conf_rank, def_rank, team_pd_pg and coach per team-season, from REG
    games played in weeks 1 through `through_week`. coach is the head coach in the latest game."""
    g = load_schedules(seasons)
    g = g[(g["game_type"] == "REG") & (g["week"] <= through_week) & g["result"].notna()]
    # One row per team per game. `result` is home score minus away score.
    games = pd.concat([
        pd.DataFrame({"season": g["season"], "week": g["week"], "team": g["home_team"], "coach": g["home_coach"],
                      "margin": g["result"], "allowed": g["away_score"]}),
        pd.DataFrame({"season": g["season"], "week": g["week"], "team": g["away_team"], "coach": g["away_coach"],
                      "margin": -g["result"], "allowed": g["home_score"]}),
    ]).sort_values("week")
    games["team"] = games["team"].replace(OLD_TEAM_CODES)
    games["win"] = (games["margin"] > 0) + 0.5 * (games["margin"] == 0)  # a tie counts as half a win
    t = games.groupby(["season", "team"], as_index=False).agg(
        team_games=("win", "size"), team_win_pct=("win", "mean"),
        team_wins=("margin", lambda m: (m > 0).sum()), team_losses=("margin", lambda m: (m < 0).sum()),
        team_ties=("margin", lambda m: (m == 0).sum()), team_pa_pg=("allowed", "mean"),
        team_pd_pg=("margin", "mean"), coach=("coach", "last"),
    )
    # 1 = fewest points allowed per game in the league that season
    t["def_rank"] = t.groupby("season")["team_pa_pg"].rank(method="min")
    conf = nfl.load_teams().to_pandas().set_index("team_abbr")["team_conf"]
    t["conf"] = t["team"].map(conf).where(~((t["team"] == "SEA") & (t["season"] < 2002)), "AFC")  # SEA moved in 2002
    # 1 = best record in the conference (ties share the better rank). A stand-in for playoff seed
    # that also works mid-season.
    t["conf_rank"] = t.groupby(["season", "conf"])["team_win_pct"].rank(method="min", ascending=False)
    return t
