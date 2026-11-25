"""Leave-one-season-out evaluation of the award models.

python -m awards.evaluate          MVP
python -m awards.evaluate opoy     Offensive Player of the Year
python -m awards.evaluate oroy     Offensive Rookie of the Year
python -m awards.evaluate dpoy     Defensive Player of the Year
python -m awards.evaluate droy     Defensive Rookie of the Year

The three offensive awards use the same features (awards/model.py). For OPOY, swapping conf_rank for team_win_pct
scored 18/24 at full season but 5/17 at week 8 and 6/16 at week 11, and the dashboard is read
mid-season, so the shared set stayed.

OROY ranks rookies only (ROOKIE_BARS in awards/features.py). Logistic, winner top pick / top 3 at weeks
8, 11, 14 and full season: shared set 12/21 15/24 20/25 17/26; plus log draft slot 12/20 12/23 18/26
18/26; minus turnovers_z 13/21 14/24 19/24 17/25; minus conf_rank 13/20 14/24 18/25 17/25; draft slot
without conf_rank 13/20 14/22 17/26 16/27. None did better at weeks 11 and 14 and full season together,
so the shared set stayed.

DPOY ranks the defensive pool (about 215 a season) on per-game sacks, interceptions, passes defended,
forced fumbles, solo tackles and defensive TDs, z-scored within DL, LB and DB, plus conf_rank and
availability. That baseline is the floor, and it is weak: voters reward reputation and team defense,
and counting stats miss box safeties and shutdown corners (Bob Sanders 2007, Pat Surtain 2024).
Logistic, top pick / top 3 at weeks 8, 11, 14 and full season: baseline 2/6 2/10 4/10 4/12; minus
tackles_z 3/6 3/8 4/11 3/10; plus def_rank (team points allowed) 3/8 3/7 3/9 4/12; plus last season's
DPOY first-place share 4/5 6/9 5/12 5/13; all three changes 4/9 5/8 5/12 4/11. Last season's vote
gained top picks at every week (+4 at week 11) and top-3 at week 14 and full season, giving back one
top-3 season at weeks 8 and 11, within noise. It is the set used.

DROY ranks defensive rookies (DEF_ROOKIE_BARS) on the defensive baseline, the floor: 7/13 7/16 7/17
8/17. Plus log draft slot 8/14 10/17 10/17 11/18; minus tackles_z 6/11 6/15 6/15 7/17; plus def_rank
6/12 9/15 10/17 8/19; minus conf_rank 8/13 7/17 8/18 9/18. Draft slot did better at every week and is
the set used. (For OROY the same feature lost at weeks 11 and 14.)

For each season 1999-2025: train on full-season features from the other 26 seasons, then score the
held-out season with features through weeks 8, 11, 14 and the full season. Seasons are held out
whole because players in the same season compete for the same votes.
"""
import sys

import pandas as pd

from awards.data import VOTES_CSV, add_targets
from awards.features import FINAL_WEEK, award_pool, build_features
from awards.model import MODELS, fit, score

SEASONS = range(1999, 2026)
WEEKS = [8, 11, 14, FINAL_WEEK]
# From the throwaway prototype (logistic, v1 features): (winner is top pick, winner in top 3) out of 27.
# The plan gives OPOY a full-season floor only. The other awards' floors are their own baselines (the
# shared features, or the defensive baseline, above), because the plan gives them none.
FLOOR = {
    "mvp": {8: (11, 17), 11: (13, 21), 14: (14, 23), FINAL_WEEK: (16, 24)},
    "opoy": {FINAL_WEEK: (14, 22)},
    "oroy": {8: (12, 21), 11: (15, 24), 14: (20, 25), FINAL_WEEK: (17, 26)},
    "dpoy": {8: (2, 6), 11: (2, 10), 14: (4, 10), FINAL_WEEK: (4, 12)},
    "droy": {8: (7, 13), 11: (7, 16), 14: (7, 17), FINAL_WEEK: (8, 17)},
}


def week_label(week):
    return "full season" if week == FINAL_WEEK else f"week {week}"


def run(award="mvp"):
    """One row per model, snapshot week and held-out season, with where the actual winner ranked."""
    snapshots = {week: award_pool(add_targets(build_features(SEASONS, week)), award) for week in WEEKS}
    full = snapshots[FINAL_WEEK]
    rows = []
    for kind in MODELS:
        for season in SEASONS:
            model = fit(kind, full[full["season"] != season], award)
            for week, table in snapshots.items():
                t = table[table["season"] == season]
                t = t.assign(score=score(kind, model, t)).sort_values("score", ascending=False)
                t["pred_rank"] = range(1, len(t) + 1)
                winners = t[t[f"won_{award}"] == 1]
                rows.append({
                    "model": kind, "week": week, "season": season,
                    # co-winners (2003 MVP): count the better-ranked one. NaN = winner not in that week's pool.
                    "winner_rank": winners["pred_rank"].min() if len(winners) else float("nan"),
                    "top_pick": t["player"].iloc[0],
                    "scores": t[["pfr_id", "player", "score"]],
                })
    return pd.DataFrame(rows)


def main(award="mvp"):
    results = run(award)
    full = award_pool(add_targets(build_features(SEASONS, FINAL_WEEK)), award)
    winners = full[full[f"won_{award}"] == 1].groupby("season")["player"].agg(" / ".join)
    n = len(SEASONS)

    print(f"{award.upper()}: leave-one-season-out, {n} seasons. Cells are seasons where the actual"
          " winner was the model's top pick / in its top 3.\n")
    print(f"{'features through':<17}" + "".join(f"{k:>16}" for k in MODELS) + f"{'floor (logistic)':>19}")
    for week in WEEKS:
        cells = []
        for kind in MODELS:
            r = results[(results["model"] == kind) & (results["week"] == week)]["winner_rank"]
            cells.append(f"{(r == 1).sum():>2} / {(r <= 3).sum():>2} of {n}")
        floor = FLOOR[award].get(week)
        floor_cell = f"{floor[0]:>9} / {floor[1]:>2} of {n}" if floor else f"{'–':>15}"
        print(f"{week_label(week):<17}" + "".join(f"{c:>16}" for c in cells) + floor_cell)

    for kind in MODELS:
        r = results[(results["model"] == kind) & (results["week"] == FINAL_WEEK) & (results["winner_rank"] != 1)]
        print(f"\n{kind} misses, full season (winner rank, model's top pick):")
        for x in r.itertuples():
            print(f"  {x.season}  {winners[x.season]:<34} ranked {x.winner_rank:>3.0f}   top pick: {x.top_pick}")

    # 2022 on, ballots rank 3-5 players, so the points order says how voters ranked the whole field.
    votes = pd.read_csv(VOTES_CSV, skiprows=2)
    votes = votes[(votes["award"] == award) & (votes["voting_system"] == "ranked_points")].dropna(subset=["votes"])
    print("\nrank correlation (Spearman) with the ranked points order, vote-getters in the pool, full season:")
    print("  season" + "".join(f"{k:>10}" for k in MODELS) + "   players")
    for season in sorted(votes["season"].unique()):
        cells = []
        for kind in MODELS:
            r = results[(results["model"] == kind) & (results["week"] == FINAL_WEEK) & (results["season"] == season)]
            both = r["scores"].iloc[0].merge(votes[votes["season"] == season][["pfr_id", "votes"]], on="pfr_id")
            cells.append(both["score"].corr(both["votes"], method="spearman"))
        print(f"  {season}" + "".join(f"{c:>10.2f}" for c in cells) + f"{len(both):>10}")


if __name__ == "__main__":
    award = sys.argv[1] if len(sys.argv) > 1 else "mvp"
    if award not in FLOOR:
        raise SystemExit(f"unknown award {award!r}; choose from {', '.join(FLOOR)}")
    main(award)
