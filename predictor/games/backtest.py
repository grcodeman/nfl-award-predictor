"""Backtests: replay past seasons through a game model and score it the way the ledger scores live picks.

The backtest covers 2015-2025, the seasons after games-elo's tuning window (2002-2014). Each game's
numbers come from the same predict(games) function the live picks use, which only lets a game see the
games before it. Next to the model are the closing line and "home", always the home team (it wins with
the home win rate and margin of 2002-2014). These are replays, not picks made at the time, and every
file says so ("kind": "backtest").

Written to predictions/games/backtest/{model}-{version}.json: totals, by season, by part of the season
(weeks 1-4, weeks 5-18, playoffs), and every game on one line each.
"""
import json
from datetime import datetime, timezone

from predictor.games import MODELS
from predictor.games.ledger import GAMES_OUT, market_prob, score, stamp
from predictor.models import version

FIRST, LAST = 2015, 2025
TUNED = (2002, 2014)


def phase(r):
    if r.game_type != "REG":
        return "playoffs"
    return "weeks 1-4" if r.week <= 4 else "weeks 5-18"


def scores(rows, home_rate, home_margin):
    """The model, the closing line and the home team over decided (untied) games."""
    d = [r for r in rows if r["result"] != 0]
    won = [int(r["result"] > 0) for r in d]
    margin = [r["result"] for r in d]
    lined = [(r, w) for r, w in zip(d, won) if r["closing_spread"] is not None]
    return [
        {"scorer": rows[0]["model"], "version": rows[0]["version"],
         **score([r["home_win_prob"] for r in d], won, [r["home_margin"] for r in d], margin)},
        {"scorer": "closing", "version": None,
         **score([market_prob(r["closing_spread"]) for r, _ in lined], [w for _, w in lined],
                 [r["closing_spread"] for r, _ in lined], [r["result"] for r, _ in lined])},
        {"scorer": "home", "version": None,
         **score([home_rate] * len(d), won, [home_margin] * len(d), margin)},
    ]


def backtest(games, name):
    """Write one model's backtest file and return its path and 2015-2025 totals."""
    pred = MODELS[name](games).set_index("game_id")
    tuned = games[games["season"].between(*TUNED) & games["result"].notna() & (games["result"] != 0)]
    home_rate, home_margin = float((tuned["result"] > 0).mean()), float(tuned["result"].mean())
    d = games[games["season"].between(FIRST, LAST) & games["result"].notna()].sort_values(["kickoff", "game_id"])
    rows = [{
        "game_id": r.game_id, "season": int(r.season), "week": int(r.week), "phase": phase(r),
        "away": r.away_team, "home": r.home_team, "away_score": int(r.away_score), "home_score": int(r.home_score),
        "result": int(r.result), "model": name, "version": version(name),
        "home_win_prob": round(float(pred.at[r.game_id, "home_win_prob"]), 4),
        "home_margin": round(float(pred.at[r.game_id, "home_margin"]), 1),
        "closing_spread": None if r.spread_line != r.spread_line else float(r.spread_line),
    } for r in d.itertuples()]
    group = lambda key: {k: scores([r for r in rows if r[key] == k], home_rate, home_margin)  # noqa: E731
                         for k in dict.fromkeys(r[key] for r in rows)}
    payload = {
        "kind": "backtest",
        "model": name,
        "version": version(name),
        "seasons": [FIRST, LAST],
        "note": f"Replayed after the fact, not live picks: each game sees only the games before it. "
                f"Parameters were picked on {TUNED[0]}-{TUNED[1]}. Ties are left out of the scores.",
        "written_at": stamp(datetime.now(timezone.utc)),
        "home_baseline": {"home_win_prob": round(home_rate, 4), "home_margin": round(home_margin, 1)},
        "totals": scores(rows, home_rate, home_margin),
        "by_season": {str(k): v for k, v in group("season").items()},
        "by_phase": group("phase"),
        "games": "__GAMES__",
    }
    keep = ["game_id", "season", "week", "phase", "away", "home", "away_score", "home_score", "home_win_prob",
            "home_margin", "closing_spread"]
    path = GAMES_OUT / "backtest" / f"{name}-{version(name)}.json"
    if path.exists():  # unchanged but for the timestamp: leave it
        old = json.loads(path.read_text())
        if {**old, "written_at": None} == {**payload, "written_at": None, "games": [
                {k: r[k] for k in keep} for r in rows]}:
            return path, payload["totals"]
    text = json.dumps(payload, indent=2)
    text = text.replace('"__GAMES__"', "[\n" + ",\n".join("    " + json.dumps({k: r[k] for k in keep}) for r in rows)
                        + "\n  ]")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n")
    return path, payload["totals"]
