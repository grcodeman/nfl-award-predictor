"""Leave-one-season-out evaluation of the MVP models.

python -m awards.evaluate

For each season 1999-2025: train on full-season features from the other 26 seasons, then score the
held-out season with features through weeks 8, 11, 14 and the full season. Seasons are held out
whole because players in the same season compete for the same votes.
"""
import pandas as pd

from awards.data import VOTES_CSV, add_targets
from awards.features import FINAL_WEEK, build_features
from awards.model import MODELS, fit, score

SEASONS = range(1999, 2026)
WEEKS = [8, 11, 14, FINAL_WEEK]
# From the throwaway prototype (logistic, v1 features): (winner is top pick, winner in top 3) out of 27.
FLOOR = {8: (11, 17), 11: (13, 21), 14: (14, 23), FINAL_WEEK: (16, 24)}


def week_label(week):
    return "full season" if week == FINAL_WEEK else f"week {week}"


def run(award="mvp"):
    """One row per model, snapshot week and held-out season, with where the actual winner ranked."""
    snapshots = {week: add_targets(build_features(SEASONS, week)) for week in WEEKS}
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
    full = add_targets(build_features(SEASONS, FINAL_WEEK))
    winners = full[full[f"won_{award}"] == 1].groupby("season")["player"].agg(" / ".join)

    print(f"{award.upper()}: leave-one-season-out, {len(SEASONS)} seasons. Cells are seasons where the actual"
          " winner was the model's top pick / in its top 3.\n")
    print(f"{'features through':<17}" + "".join(f"{k:>16}" for k in MODELS) + f"{'floor (logistic)':>19}")
    for week in WEEKS:
        cells = []
        for kind in MODELS:
            r = results[(results["model"] == kind) & (results["week"] == week)]["winner_rank"]
            cells.append(f"{(r == 1).sum():>2} / {(r <= 3).sum():>2} of 27")
        floor = FLOOR[week]
        print(f"{week_label(week):<17}" + "".join(f"{c:>16}" for c in cells) + f"{floor[0]:>9} / {floor[1]:>2} of 27")

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
    main()
