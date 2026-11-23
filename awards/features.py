"""build_features(seasons, through_week): the only way features get built.

Training calls it with the final week, the weekly run with the latest completed week, and backtests
with any week, so all three see exactly the same features.

python -m awards.features   writes the 1999-2025 table with targets to .cache/modeling_table.csv
                            and prints the Phase 1 acceptance checks
"""
import pandas as pd

from awards.data import (ROOT, VOTES_CSV, add_targets, load_player_ids, load_targets, load_team_records,
                         load_weekly_stats)

# Per team game rates, so a player 10 games in compares fairly with a full season.
RATES = ["yards", "tds", "epa", "turnovers"]
POSITIONS = ["QB", "RB", "WR", "TE"]
FINAL_WEEK = 18  # covers every regular-season week, 17-game seasons included


def zscore(col, groups):
    """0 = average for the group, +1 = one standard deviation above. A group too small to vary gets 0."""
    g = col.groupby(groups)
    return ((col - g.transform("mean")) / g.transform("std")).fillna(0)


def build_features(seasons, through_week):
    """One row per candidate player-season, using games in weeks 1 through `through_week`."""
    s = load_weekly_stats(seasons, through_week)
    s["yards"] = s["passing_yards"] + s["rushing_yards"] + s["receiving_yards"]
    s["tds"] = s["passing_tds"] + s["rushing_tds"] + s["receiving_tds"]
    s["epa"] = s["passing_epa"] + s["rushing_epa"] + s["receiving_epa"]
    s["turnovers"] = (s["passing_interceptions"] + s["sack_fumbles_lost"]
                      + s["rushing_fumbles_lost"] + s["receiving_fumbles_lost"])
    s["touches"] = s["carries"] + s["receptions"]

    # Season totals so far. "last" after sorting by week = most recent team, for players traded mid-season.
    p = s.sort_values("week").groupby(["season", "player_id"], as_index=False).agg(
        player=("player_display_name", "last"),
        position_group=("position_group", "last"),
        team=("team", "last"),
        headshot_url=("headshot_url", "last"),
        games=("week", "size"),
        **{c: (c, "sum") for c in ["attempts", "touches", "receiving_yards"] + RATES},
    )
    p = p.merge(load_team_records(seasons, through_week), on=["season", "team"], how="left", validate="many_to_one")
    assert p["team_games"].notna().all(), "a player's team has no record; check OLD_TEAM_CODES"

    per_game = p[["attempts", "touches", "receiving_yards"] + RATES].div(p["team_games"], axis=0)
    # A traded player can have more games than his new team has played, so cap at 1.
    p["availability"] = (p["games"] / p["team_games"]).clip(upper=1)

    # Candidate pool: players getting a starter's workload, judged per team game so it works mid-season.
    pos = p["position_group"]
    in_pool = (
        ((pos == "QB") & (per_game["attempts"] >= 14))
        | ((pos == "RB") & (per_game["touches"] >= 12))
        | (pos.isin(["WR", "TE"]) & (per_game["receiving_yards"] >= 50))
    )
    p = p[in_pool].copy()
    for c in RATES:
        p[f"{c}_pg"] = per_game.loc[p.index, c]

    # z-score each rate against the other candidates at the same position that season:
    # 0 = an average candidate, +1 = one standard deviation better. TEs are grouped with WRs
    # because some seasons have only 1 or 2 TEs in the pool, too few for a z-score to mean anything.
    z_group = [p["season"], p["position_group"].replace({"TE": "WR"})]
    for c in RATES:
        p[f"{c}_z"] = zscore(p[f"{c}_pg"], z_group)

    for position in POSITIONS:
        p[f"is_{position.lower()}"] = (p["position_group"] == position).astype(int)

    p = p.merge(load_player_ids(), on="player_id", how="left", validate="many_to_one")
    keep = ["season", "player_id", "pfr_id", "player", "position_group", "team", "headshot_url",
            "games", "team_games", "team_win_pct", "availability"]
    keep += [f"{c}_pg" for c in RATES] + [f"{c}_z" for c in RATES] + [f"is_{x.lower()}" for x in POSITIONS]
    keep += ["conf_rank", "team_wins", "team_losses", "team_ties"] + RATES  # record and season totals, for display
    return p[keep].sort_values(["season", "epa_z"], ascending=[True, False]).reset_index(drop=True)


def main():
    seasons = range(1999, 2026)
    table = add_targets(build_features(seasons, FINAL_WEEK))
    targets = load_targets()
    out = ROOT / ".cache" / "modeling_table.csv"
    table.to_csv(out, index=False)
    print(f"wrote {len(table)} rows to {out.relative_to(ROOT)}\n")

    per_season = table.groupby("season").size()
    print(f"rows per season: min {per_season.min()}, median {per_season.median():.0f}, max {per_season.max()}"
          f" over {per_season.size} seasons")

    # Vote-getters who are not in the pool, with their name and position from the vote file.
    voters = pd.read_csv(VOTES_CSV, skiprows=2)[["season", "award", "player", "pfr_id", "pos"]]
    for award in ["mvp", "opoy"]:
        sums = table.groupby("season")[f"target_{award}"].sum()
        print(f"\nin-pool target_{award}: sums to 1.0 in {(sums.round(3) >= 1.0).sum()} of {sums.size} seasons,"
              f" max {sums.max():.3f}")
        missing = targets[targets[f"target_{award}"] > 0].merge(table[["pfr_id", "season"]], how="left", indicator=True)
        missing = missing[missing["_merge"] == "left_only"].merge(voters[voters["award"] == award], on=["pfr_id", "season"])
        for season, total in sums[sums.round(3) < 1.0].items():
            who = missing[missing["season"] == season]
            names = ", ".join(f"{r.player} ({r.pos}, {getattr(r, f'target_{award}'):.2f})" for r in who.itertuples())
            print(f"  {season}: {total:.3f}  missing: {names}")

    print("\nspot checks (should be the top target_mvp of their season):")
    for season, name in [(2007, "Tom Brady"), (2012, "Adrian Peterson"), (2024, "Josh Allen")]:
        top = table[table["season"] == season].nlargest(1, "target_mvp").iloc[0]
        print(f"  {season} {name}: top is {top['player']} ({top['target_mvp']:.2f})"
              f" {'OK' if top['player'] == name else 'MISMATCH'}")

    now = build_features([2026], through_week=10)
    print(f"\n2026 through week 10: {len(now)} candidates, {now.isna().sum().sum()} missing values,"
          f" by position {now['position_group'].value_counts().to_dict()}")
    print(now.head(8)[["player", "position_group", "team", "games", "team_win_pct", "yards_pg", "tds_pg", "epa_z"]]
          .to_string(index=False, float_format="%.2f"))


if __name__ == "__main__":
    main()
