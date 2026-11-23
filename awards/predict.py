"""Weekly predictions: retrain, score the season through a week, write the dashboard JSON.

python -m awards.predict                          latest completed week of the current season,
                                                  skipped if that week's file already exists
python -m awards.predict --season 2026 --week 5   rebuild any completed week (backfill)

Writes predictions/{season}/week_{WW}.json, a copy of the newest week at predictions/latest.json,
predictions/index.json listing every week available, and predictions/teams.json with the team
colors and logos the dashboard uses. Training takes seconds, so the model is refit on every run
instead of being saved.
"""
import argparse
import json
import shutil
from datetime import datetime, timezone

import nflreadpy as nfl

from awards.data import ROOT, add_targets, load_targets, load_weekly_stats
from awards.features import FINAL_WEEK, build_features
from awards.model import MODEL_VERSION, fit, score, to_shares

OUT = ROOT / "predictions"
KIND = "logistic"  # the model that cleared the Phase 2 floor at every snapshot week
AWARDS = ["mvp"]
TOP_N = 10


def latest_completed_week(season):
    """Highest week where every regular-season game has a result and published player stats.

    nflverse posts player stats a few hours after the games, so a week can be finished on the
    schedule before its stats exist. Returns None if no week is complete yet.
    """
    g = nfl.load_schedules([season]).to_pandas()
    g = g[g["game_type"] == "REG"]
    played = g["result"].notna()
    if not played.any():  # before week 1 there is no stats file for the season either
        return None
    has_stats = g["game_id"].isin(load_weekly_stats([season], FINAL_WEEK)["game_id"])
    done = (played & has_stats).groupby(g["week"]).all()
    return int(done[done].index.max()) if done.any() else None


def ranked(season, week, model):
    """Every candidate through `week`, scored and ranked, with shares that sum to 1 over the pool."""
    t = build_features([season], week)
    t["score"] = score(KIND, model, t)
    t["share"] = to_shares(KIND, t["score"], t["season"])
    t = t.sort_values(["score", "player_id"], ascending=[False, True])  # player_id breaks ties, for stable output
    t["rank"] = range(1, len(t) + 1)
    return t.set_index("player_id")


def entry(player_id, row, prev):
    p = prev.loc[player_id] if prev is not None and player_id in prev.index else None
    record = f"{row.team_wins}-{row.team_losses}" + (f"-{row.team_ties}" if row.team_ties else "")
    return {
        "rank": int(row["rank"]),
        "prev_rank": int(p["rank"]) if p is not None else None,
        "player_id": player_id,
        "player": row.player,
        "position": row.position_group,
        "team": row.team,
        "team_record": record,
        "headshot_url": row.headshot_url if isinstance(row.headshot_url, str) else None,
        "share": round(float(row.share), 3),
        "prev_share": round(float(p["share"]), 3) if p is not None else None,
        "stats": {
            "games": int(row.games),
            "yards_per_game": round(float(row.yards / row.games), 1),
            "tds": int(row.tds),
            "turnovers": int(row.turnovers),
            "epa_per_game": round(float(row.epa / row.games), 1),
        },
    }


def write_if_changed(path, payload):
    """Write the file unless only generated_at would change, so rerunning a week leaves it untouched."""
    if path.exists() and {**json.loads(path.read_text()), "generated_at": None} == {**payload, "generated_at": None}:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return True


def write_teams():
    """teams.json: the name, color and logo the dashboard shows for each team code."""
    t = nfl.load_teams().to_pandas()
    teams = {r.team_abbr: {"name": r.team_name, "color": r.team_color, "logo": r.team_logo_espn} for r in t.itertuples()}
    write_if_changed(OUT / "teams.json", teams)


def write_index():
    """index.json lists every week on disk; latest.json is a copy of the newest one."""
    weeks = sorted((int(f.parent.name), int(f.stem.split("_")[1])) for f in OUT.glob("*/week_*.json"))
    seasons = {}
    for season, week in weeks:
        seasons.setdefault(str(season), []).append(week)
    latest_season, latest_week = weeks[-1]
    write_if_changed(OUT / "index.json", {"latest": {"season": latest_season, "week": latest_week}, "seasons": seasons})
    shutil.copyfile(OUT / str(latest_season) / f"week_{latest_week:02d}.json", OUT / "latest.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--season", type=int, default=nfl.get_current_season())
    parser.add_argument("--week", type=int, help="default: the latest completed week")
    args = parser.parse_args()

    latest = latest_completed_week(args.season)
    if latest is None:
        print(f"{args.season}: no completed weeks yet, nothing to do")
        return
    week = args.week or latest
    if week > latest:
        raise SystemExit(f"{args.season} week {week} isn't complete yet (latest completed week is {latest})")
    path = OUT / str(args.season) / f"week_{week:02d}.json"
    # The weekly run skips a week it already has, which makes the Wednesday run a safety net and the
    # offseason a no-op. Passing --week rebuilds that week regardless.
    if args.week is None and path.exists():
        print(f"{args.season} week {week} is already in {path.relative_to(ROOT)}, nothing to do")
        return

    # Train on every season with votes except the one being predicted, as in the evaluation.
    train_seasons = sorted(set(load_targets()["season"]) - {args.season})
    train = add_targets(build_features(train_seasons, FINAL_WEEK))

    payload = {
        "season": args.season,
        "through_week": week,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model_version": MODEL_VERSION,
        "awards": {},
    }
    for award in AWARDS:
        model = fit(KIND, train, award)
        now = ranked(args.season, week, model)
        prev = ranked(args.season, week - 1, model) if week > 1 else None
        payload["awards"][award] = [entry(pid, row, prev) for pid, row in now.head(TOP_N).iterrows()]

    changed = write_if_changed(path, payload)
    write_index()
    write_teams()

    print(f"{args.season} through week {week}: {'wrote' if changed else 'unchanged'} {path.relative_to(ROOT)}"
          f" (trained on {train_seasons[0]}-{train_seasons[-1]}, {len(train)} rows)")
    for award, rows in payload["awards"].items():
        print(f"  {award.upper()}")
        for r in rows[:5]:
            move = "new" if r["prev_rank"] is None else f"{r['prev_rank'] - r['rank']:+d}"
            print(f"  {r['rank']:>3}. {r['player']:<22} {r['position']:<3} {r['team']:<4} {r['team_record']:<6}"
                  f" share {r['share']:.3f}  ({move} since last week)")


if __name__ == "__main__":
    main()
