"""Loaders: AP vote targets, the player id crosswalk, weekly player stats, and team records."""
from pathlib import Path

import nflreadpy as nfl
import pandas as pd
from nflreadpy.config import update_config

ROOT = Path(__file__).resolve().parent.parent
VOTES_CSV = ROOT / "award-share-data" / "award_votes.csv"

# Keep nflreadpy downloads on disk in the gitignored .cache/ folder; it re-downloads at most once a day.
update_config(cache_mode="filesystem", cache_dir=ROOT / ".cache" / "nflreadpy", verbose=False)

# Schedules use the team code of the time; stats use today's code for every season.
OLD_TEAM_CODES = {"STL": "LA", "SD": "LAC", "OAK": "LV"}

ID_COLS = ["season", "week", "player_id", "player_display_name", "position_group", "team", "headshot_url"]
STAT_COLS = [
    "attempts", "carries", "receptions",
    "passing_yards", "rushing_yards", "receiving_yards",
    "passing_tds", "rushing_tds", "receiving_tds",
    "passing_epa", "rushing_epa", "receiving_epa",
    "passing_interceptions", "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost",
]


def load_targets(awards=("mvp", "opoy")):
    """One row per player-season that got votes: pfr_id, season, target_* and won_* for each award.

    target_* is first-place share. Unlike `share`, it sums to 1.0 within every season and award,
    so it means the same thing before and after the 2022 switch to ranked ballots.
    won_* is 1 for the winner, from the award-data/ winner files, which list both 2003 co-MVPs.
    """
    v = pd.read_csv(VOTES_CSV, skiprows=2)
    v = v[v["award"].isin(awards)].dropna(subset=["pfr_id"])  # drops Denny Kellington, a team trainer (2022 MVP)
    first = v["first_place"].fillna(0)
    total_first = first.groupby([v["season"], v["award"]]).transform("sum")
    # single_vote seasons: every vote was a first-place vote, so share already is first-place share
    v["target"] = v["share"].where(v["voting_system"] == "single_vote", first / total_first)
    wide = v.pivot_table(index=["pfr_id", "season"], columns="award", values="target", aggfunc="sum", fill_value=0)
    wide = wide.add_prefix("target_").reset_index().rename_axis(columns=None)
    for award in awards:
        w = pd.read_csv(ROOT / "award-data" / f"{award}.csv", skiprows=2)
        winners = set(zip(w["Player-additional"], w["Year"]))
        wide[f"won_{award}"] = [int(key in winners) for key in zip(wide["pfr_id"], wide["season"])]
    return wide


def add_targets(table):
    """Attach target_* and won_* to a build_features table; 0 for players who got no votes."""
    t = table.merge(load_targets(), on=["pfr_id", "season"], how="left", validate="many_to_one")
    cols = [c for c in t.columns if c.startswith(("target_", "won_"))]
    t[cols] = t[cols].fillna(0)
    return t


def load_player_ids():
    """player_id (the gsis id used in nflverse stats) -> pfr_id (Pro Football Reference, used in the vote file)."""
    players = nfl.load_players().to_pandas()
    return players[["gsis_id", "pfr_id"]].rename(columns={"gsis_id": "player_id"})


def load_weekly_stats(seasons, through_week):
    """Regular-season player stats, one row per player per game, weeks 1 through `through_week`."""
    s = nfl.load_player_stats(list(seasons), summary_level="week").to_pandas()
    # one 1999 row (Steve Bono, week 9) has no team; it can't be matched to a team record
    s = s[(s["season_type"] == "REG") & (s["week"] <= through_week) & s["player_id"].notna() & s["team"].notna()]
    return s[ID_COLS + STAT_COLS].fillna({c: 0 for c in STAT_COLS})  # EPA is blank when a player had no such plays


def load_team_records(seasons, through_week):
    """team_games and team_win_pct per team-season, from REG games played in weeks 1 through `through_week`."""
    g = nfl.load_schedules(list(seasons)).to_pandas()
    g = g[(g["game_type"] == "REG") & (g["week"] <= through_week) & g["result"].notna()]
    # One row per team per game. `result` is home score minus away score.
    games = pd.concat([
        pd.DataFrame({"season": g["season"], "team": g["home_team"], "margin": g["result"]}),
        pd.DataFrame({"season": g["season"], "team": g["away_team"], "margin": -g["result"]}),
    ])
    games["team"] = games["team"].replace(OLD_TEAM_CODES)
    games["win"] = (games["margin"] > 0) + 0.5 * (games["margin"] == 0)  # a tie counts as half a win
    t = games.groupby(["season", "team"], as_index=False).agg(team_games=("win", "size"), team_win_pct=("win", "mean"))
    conf = nfl.load_teams().to_pandas().set_index("team_abbr")["team_conf"]
    t["conf"] = t["team"].map(conf).where(~((t["team"] == "SEA") & (t["season"] < 2002)), "AFC")  # SEA moved in 2002
    # 1 = best record in the conference (ties share the better rank). A stand-in for playoff seed
    # that also works mid-season.
    t["conf_rank"] = t.groupby(["season", "conf"])["team_win_pct"].rank(method="min", ascending=False)
    return t
