"""The pick ledger: every model's picks, written before kickoff and never rewritten, then graded.

predictions/games/picks/{season}/week_{WW}.json    live picks for one week. Written once, before the week's
                                                   first kickoff: write_picks refuses after that, and
                                                   refuses to overwrite. The git commit time is the proof.
predictions/games/results/{season}/week_{WW}.json  each picked game's result and every scorer's numbers for
                                                   the week, rewritten as games finish
predictions/games/scoreboard.json                  season totals and week-by-week numbers for each scorer

Scorers are every model version with picks in the file, plus two from the betting market: "market", the
spread when the picks were written (the same news the models had), and "closing", the last spread before
kickoff (the best public forecast). A spread becomes a home win probability through a normal curve with a
13.5-point standard deviation. Ties are left out of every score, as in the backtest; there are about two a
season. The scores: winners picked (a 50% call counts half), log loss, Brier score, and the average miss
on the margin in points. Lower is better for the last three.
"""
import json
import math
from datetime import timedelta

import pandas as pd

from predictor.data import OUT, write_if_changed
from predictor.games import CHAMPION, MODELS
from predictor.models import version

GAMES_OUT = OUT / "games"
SPREAD_SD = 13.5
PICK_WINDOW = timedelta(days=6)  # picks wait until the week's first game is this close, for the latest news
# A game still without a score this long after kickoff (suspended, or the score is late) stops holding up
# the next week, so Wednesday's run writes picks even if Monday night's game never got a score.
GIVE_UP = timedelta(hours=30)
ROUNDS = {"WC": "Wild Card", "DIV": "Divisional", "CON": "Conference", "SB": "Super Bowl"}


class Locked(Exception):
    """Raised when a week's picks can't be written: a game has kicked off, or the file already exists."""


def picks_path(season, week):
    return GAMES_OUT / "picks" / str(season) / f"week_{week:02d}.json"


def results_path(season, week):
    return GAMES_OUT / "results" / str(season) / f"week_{week:02d}.json"


def stamp(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def market_prob(spread):
    """Home win probability from the spread (points the home team is favored by)."""
    return 0.5 * (1 + math.erf(spread / (SPREAD_SD * math.sqrt(2))))


def week_label(games):
    t = games["game_type"].iloc[0]
    return ROUNDS.get(t, f"Week {int(games['week'].iloc[0])}")


def next_week(games, now):
    """(season, week) to pick right now, or (None, reason). That's the first week with no game kicked off,
    once every game before it is final and its first kickoff is within PICK_WINDOW."""
    first = games.groupby(["season", "week"])["kickoff"].min()
    upcoming = first[first > now]
    if upcoming.empty:
        return None, "no unplayed week on the schedule"
    (season, week), kickoff = upcoming.index[0], upcoming.iloc[0]
    before = games[(games["kickoff"] < kickoff) & games["result"].isna() & (games["kickoff"] > now - GIVE_UP)]
    if len(before):
        return None, f"{season} week {week} waits for {len(before)} unfinished game(s) before it"
    if kickoff - now > PICK_WINDOW:
        return None, f"{season} week {week} starts {stamp(kickoff)}, more than {PICK_WINDOW.days} days out"
    return (season, week), None


def write_picks(games, season, week, now):
    """Write the week's picks from every model in MODELS. Raises Locked once any game of the week has
    kicked off or if the file exists: a pick written after kickoff isn't a pick."""
    wk = games[(games["season"] == season) & (games["week"] == week)].sort_values(["kickoff", "game_id"])
    first = wk["kickoff"].min()
    path = picks_path(season, week)
    if now >= first:
        raise Locked(f"{season} week {week} kicked off at {stamp(first)}; its picks can no longer be written")
    if path.exists():
        raise Locked(f"{season} week {week} already has picks; they are never rewritten")
    picks = []
    for name, predict in MODELS.items():
        p = predict(games).set_index("game_id").loc[wk["game_id"]]
        picks += [{"game_id": gid, "model": name, "version": version(name),
                   "home_win_prob": round(float(r.home_win_prob), 4), "home_margin": round(float(r.home_margin), 1),
                   "inputs": r.inputs} for gid, r in p.iterrows()]
    payload = {
        "kind": "live",
        "season": int(season),
        "week": int(week),
        "label": week_label(wk),
        "written_at": stamp(now),
        "first_kickoff": stamp(first),
        "champion": {"model": CHAMPION, "version": version(CHAMPION)},
        "games": [{
            "game_id": r.game_id, "kickoff": stamp(r.kickoff), "away": r.away_team, "home": r.home_team,
            "neutral": r.location == "Neutral",
            # the market at this moment: points the home team is favored by, blank if no line is posted yet
            "market_spread": None if pd.isna(r.spread_line) else float(r.spread_line),
            "away_qb": None if pd.isna(r.away_qb_name) else r.away_qb_name,
            "home_qb": None if pd.isna(r.home_qb_name) else r.home_qb_name,
        } for r in wk.itertuples()],
        "picks": picks,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def score(prob, won, margin_pred, margin):
    """One scorer's numbers over a set of decided games: arrays of home win probability, 1/0 home won,
    predicted and actual home margin."""
    n = len(prob)
    if n == 0:
        return {"games": 0, "correct": 0, "log_loss": None, "brier": None, "margin_error": None}
    p = [min(max(x, 1e-6), 1 - 1e-6) for x in prob]
    correct = sum(0.5 if x == 0.5 else float((x > 0.5) == bool(w)) for x, w in zip(prob, won))
    return {
        "games": n,
        "correct": correct,
        "log_loss": round(-sum(w * math.log(x) + (1 - w) * math.log(1 - x) for x, w in zip(p, won)) / n, 4),
        "brier": round(sum((x - w) ** 2 for x, w in zip(prob, won)) / n, 4),
        "margin_error": round(sum(abs(a - b) for a, b in zip(margin_pred, margin)) / n, 2),
    }


def score_week(picks, games):
    """Every scorer's numbers for one picks file, over its games that are final and not tied."""
    sched = games.set_index("game_id")
    rows = [g | {"result": sched.at[g["game_id"], "result"], "closing": sched.at[g["game_id"], "spread_line"]}
            for g in picks["games"]]
    decided = {r["game_id"]: r for r in rows if pd.notna(r["result"]) and r["result"] != 0}
    out = []
    for (name, ver), group in _by_model(picks["picks"]).items():
        mine = [p for p in group if p["game_id"] in decided]
        out.append({"scorer": name, "version": ver, **score(
            [p["home_win_prob"] for p in mine], [int(decided[p["game_id"]]["result"] > 0) for p in mine],
            [p["home_margin"] for p in mine], [decided[p["game_id"]]["result"] for p in mine])})
    for scorer, key in [("market", "market_spread"), ("closing", "closing")]:
        lined = [r for r in decided.values() if r[key] is not None and pd.notna(r[key])]
        out.append({"scorer": scorer, "version": None, **score(
            [market_prob(r[key]) for r in lined], [int(r["result"] > 0) for r in lined],
            [r[key] for r in lined], [r["result"] for r in lined])})
    return rows, out


def _by_model(picks):
    groups = {}
    for p in picks:
        groups.setdefault((p["model"], p["version"]), []).append(p)
    return groups


def grade(games, now):
    """Write the results file for every picks file with at least one game final. Returns the paths written."""
    written, sched = [], games.set_index("game_id")
    for path in sorted(GAMES_OUT.glob("picks/*/week_*.json")):
        picks = json.loads(path.read_text())
        rows, scores = score_week(picks, games)
        if all(pd.isna(r["result"]) for r in rows):
            continue
        final = [r for r in rows if pd.notna(r["result"])]
        payload = {
            "season": picks["season"],
            "week": picks["week"],
            "label": picks["label"],
            "graded_at": stamp(now),
            "complete": len(final) == len(rows),
            "games": [{
                "game_id": r["game_id"],
                "away_score": int(sched.at[r["game_id"], "away_score"]),
                "home_score": int(sched.at[r["game_id"], "home_score"]),
                "closing_spread": None if pd.isna(r["closing"]) else float(r["closing"]),
            } for r in final],
            "scores": scores,
        }
        out = results_path(picks["season"], picks["week"])
        if write_if_changed(out, payload, volatile=("graded_at",)):
            written.append(out)
    return written


def combine(rows):
    """Add up per-week score rows for one scorer, weighting each average by its games."""
    n = sum(r["games"] for r in rows)
    if n == 0:
        return {"games": 0, "correct": 0, "log_loss": None, "brier": None, "margin_error": None}
    avg = lambda k, d: round(sum(r[k] * r["games"] for r in rows if r["games"]) / n, d)  # noqa: E731
    return {"games": n, "correct": sum(r["correct"] for r in rows), "log_loss": avg("log_loss", 4),
            "brier": avg("brier", 4), "margin_error": avg("margin_error", 2)}


def write_scoreboard(now):
    """scoreboard.json: for each season with graded picks, every scorer's totals and its week-by-week rows."""
    seasons = {}
    for path in sorted(GAMES_OUT.glob("results/*/week_*.json")):
        r = json.loads(path.read_text())
        s = seasons.setdefault(str(r["season"]), {"weeks": [], "totals": [], "by_week": {}})
        s["weeks"].append({"week": r["week"], "label": r["label"], "complete": r["complete"]})
        s["by_week"][str(r["week"])] = r["scores"]
    for s in seasons.values():
        keys = {(x["scorer"], x["version"]) for rows in s["by_week"].values() for x in rows}
        for scorer, ver in sorted(keys, key=lambda k: (k[1] is None, k[0], k[1] or 0)):
            rows = [x for wk in s["by_week"].values() for x in wk if (x["scorer"], x["version"]) == (scorer, ver)]
            s["totals"].append({"scorer": scorer, "version": ver, **combine(rows)})
    payload = {
        "kind": "live",
        "updated_at": stamp(now),
        "champion": {"model": CHAMPION, "version": version(CHAMPION)},
        "backtest": f"games/backtest/{CHAMPION}-{version(CHAMPION)}.json",
        "seasons": seasons,
    }
    return write_if_changed(GAMES_OUT / "scoreboard.json", payload, volatile=("updated_at",))
