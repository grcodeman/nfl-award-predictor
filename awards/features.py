"""build_features(seasons, through_week): the only way features get built.

Training calls it with the final week, the weekly run with the latest completed week, and backtests
with any week, so all three see exactly the same features. The table holds every award's candidates;
award_pool(table, award) picks the rows one award ranks.

python -m awards.features   writes the 1999-2025 table with targets to .cache/modeling_table.csv
                            and prints the Phase 1 acceptance checks
"""
import numpy as np
import pandas as pd

from awards.data import (ROOT, VOTES_CSV, add_targets, load_player_ids, load_targets, load_team_records,
                         load_weekly_stats)

# Per team game rates, so a player 10 games in compares fairly with a full season.
RATES = ["yards", "tds", "epa", "turnovers"]
DEF_RATES = ["sacks", "ints", "pds", "ffs", "tackles", "def_tds"]  # tackles = solo tackles
POSITIONS = ["QB", "RB", "WR", "TE"]
DEF_POSITIONS = ["DL", "LB", "DB"]
FINAL_WEEK = 18  # covers every regular-season week, 17-game seasons included

# Offensive workload bars per team game: QB pass attempts, RB touches, WR/TE receiving yards. Starters
# clear the first set. Rookies get a much lower one: few clear the starter bars (8 a season, and 1 in 2026
# through week 11), which missed Percy Harvin (2009 OROY, 49.4 yards a team game) and couldn't fill
# a top 10. 8/8/35 still left 2026 weeks 2-7 with 4 to 9 rookies; 5/5/25 keeps 14 or more.
STARTER_BARS = (14, 12, 50)
ROOKIE_BARS = (5, 5, 25)
# Defensive starter bars per team game, either one: DL sacks + forced fumbles or solo tackles, LB solo
# tackles or sacks, DB interceptions + passes defended or solo tackles. They sit at a regular starter's
# level, not a stat leader's, because DPOY often goes to players with modest counting stats (Bob Sanders
# 2007, 2.6 solo tackles; Patrick Surtain 2024, 0.9 INT + PD). That makes about 215 a season, twice the
# offensive pool; bars sized for 100 lost both of those winners.
DEF_STARTER_BARS = {"DL": (0.35, 2.5), "LB": (3.25, 0.35), "DB": (0.75, 2.5)}

# Which candidates each award ranks. Rookies below the starter bars are candidates only for rookie awards.
POOLS = {
    "mvp": lambda t: (t["side"] == "offense") & (t["starter"] == 1),
    "opoy": lambda t: (t["side"] == "offense") & (t["starter"] == 1),
    "oroy": lambda t: (t["side"] == "offense") & (t["rookie"] == 1),
    "dpoy": lambda t: (t["side"] == "defense") & (t["starter"] == 1),
}


def award_pool(table, award):
    """The rows of a build_features table that `award` ranks, in table order."""
    return table[POOLS[award](table)]


def zscore(col, groups, ref):
    """0 = average for the group's reference rows, +1 = one standard deviation above. Every row is scored
    against the reference rows of its group, so a rookie below the starter bars is compared with the
    starters. A group with no reference rows, or too few to vary, gets 0."""
    stats = col[ref].groupby([g[ref] for g in groups]).agg(["mean", "std"])
    at = pd.MultiIndex.from_arrays(groups)
    mean, std = stats["mean"].reindex(at).to_numpy(), stats["std"].reindex(at).to_numpy()
    # no spread (every starter at 0 defensive TDs in week 1) would put a rookie off the scale at +-inf
    std = np.where(std > 0, std, np.nan)
    return pd.Series((col.to_numpy() - mean) / std, index=col.index).fillna(0)


def build_features(seasons, through_week):
    """One row per candidate player-season, using games in weeks 1 through `through_week`.

    side is "offense" or "defense"; starter and rookie say which pools the row is in. A row's z-scores
    for the other side are 0.
    """
    s = load_weekly_stats(seasons, through_week)
    s["yards"] = s["passing_yards"] + s["rushing_yards"] + s["receiving_yards"]
    s["tds"] = s["passing_tds"] + s["rushing_tds"] + s["receiving_tds"]
    s["epa"] = s["passing_epa"] + s["rushing_epa"] + s["receiving_epa"]
    s["turnovers"] = (s["passing_interceptions"] + s["sack_fumbles_lost"]
                      + s["rushing_fumbles_lost"] + s["receiving_fumbles_lost"])
    s["touches"] = s["carries"] + s["receptions"]
    s = s.rename(columns={"def_sacks": "sacks", "def_interceptions": "ints", "def_pass_defended": "pds",
                          "def_fumbles_forced": "ffs", "def_tackles_solo": "tackles"})

    # Season totals so far. "last" after sorting by week = most recent team, for players traded mid-season.
    p = s.sort_values("week").groupby(["season", "player_id"], as_index=False).agg(
        player=("player_display_name", "last"),
        position=("position", "last"),
        position_group=("position_group", "last"),
        team=("team", "last"),
        headshot_url=("headshot_url", "last"),
        games=("week", "size"),
        **{c: (c, "sum") for c in ["attempts", "touches", "receiving_yards"] + RATES + DEF_RATES},
    )
    p = p.merge(load_team_records(seasons, through_week), on=["season", "team"], how="left", validate="many_to_one")
    assert p["team_games"].notna().all(), "a player's team has no record; check OLD_TEAM_CODES"
    p = p.merge(load_player_ids(), on="player_id", how="left", validate="many_to_one")
    # Last season's first-place share of the DPOY vote, known before the season starts. Defensive voting
    # leans on reputation (awards/evaluate.py). 0 for 1999, the first season of vote data.
    prev = load_targets(("dpoy",))[["pfr_id", "season", "target_dpoy"]]
    prev = prev.assign(season=prev["season"] + 1).rename(columns={"target_dpoy": "prev_dpoy_vote"})
    p = p.merge(prev, on=["pfr_id", "season"], how="left", validate="many_to_one").fillna({"prev_dpoy_vote": 0})

    per_game = p[["attempts", "touches", "receiving_yards"] + RATES + DEF_RATES].div(p["team_games"], axis=0)
    # A traded player can have more games than his new team has played, so cap at 1.
    p["availability"] = (p["games"] / p["team_games"]).clip(upper=1)
    pos = p["position_group"]
    is_rookie = p["rookie_season"] == p["season"]

    # Candidate pools: players getting a starter's workload, judged per team game so it works mid-season.
    def clears(bars):
        qb, rb, wr = bars
        return (((pos == "QB") & (per_game["attempts"] >= qb)) | ((pos == "RB") & (per_game["touches"] >= rb))
                | (pos.isin(["WR", "TE"]) & (per_game["receiving_yards"] >= wr)))

    def clears_defense(bars):
        g = per_game
        return (((pos == "DL") & ((g["sacks"] + g["ffs"] >= bars["DL"][0]) | (g["tackles"] >= bars["DL"][1])))
                | ((pos == "LB") & ((g["tackles"] >= bars["LB"][0]) | (g["sacks"] >= bars["LB"][1])))
                | ((pos == "DB") & ((g["ints"] + g["pds"] >= bars["DB"][0]) | (g["tackles"] >= bars["DB"][1]))))

    offense, defense = pos.isin(POSITIONS), pos.isin(DEF_POSITIONS)
    p["side"] = defense.map({True: "defense", False: "offense"})
    p["starter"] = ((offense & clears(STARTER_BARS)) | (defense & clears_defense(DEF_STARTER_BARS))).astype(int)
    p["rookie"] = (offense & is_rookie & clears(ROOKIE_BARS)).astype(int)
    p = p[(p["starter"] == 1) | (p["rookie"] == 1)].copy()
    for c in RATES + DEF_RATES:
        p[f"{c}_pg"] = per_game.loc[p.index, c]

    # z-score each rate against that side's starters at the same position that season:
    # 0 = an average starter, +1 = one standard deviation better. TEs are grouped with WRs
    # because some seasons have only 1 or 2 TEs in the pool, too few for a z-score to mean anything.
    z_group = [p["season"], p["position_group"].replace({"TE": "WR"})]
    for c in RATES:
        p[f"{c}_z"] = zscore(p[f"{c}_pg"], z_group, (p["side"] == "offense") & (p["starter"] == 1))
    for c in DEF_RATES:
        p[f"{c}_z"] = zscore(p[f"{c}_pg"], z_group, (p["side"] == "defense") & (p["starter"] == 1))

    for position in POSITIONS + DEF_POSITIONS:
        p[f"is_{position.lower()}"] = (p["position_group"] == position).astype(int)

    keep = ["season", "player_id", "pfr_id", "player", "position", "position_group", "side", "team", "headshot_url",
            "games", "team_games", "team_win_pct", "availability", "starter", "rookie"]
    keep += [f"{c}_pg" for c in RATES + DEF_RATES] + [f"{c}_z" for c in RATES + DEF_RATES]
    keep += [f"is_{x.lower()}" for x in POSITIONS + DEF_POSITIONS]
    keep += ["conf_rank", "def_rank", "prev_dpoy_vote", "team_wins", "team_losses", "team_ties"]
    keep += RATES + DEF_RATES  # record and season totals, for display
    # Offense first, in the order it has always had, so the offensive awards fit on identical rows.
    return pd.concat([
        p.loc[p["side"] == "offense", keep].sort_values(["season", "epa_z"], ascending=[True, False]),
        p.loc[p["side"] == "defense", keep].sort_values(["season", "player_id"]),
    ]).reset_index(drop=True)


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

    # Vote-getters who are not in the award's pool, with their name and position from the vote file.
    voters = pd.read_csv(VOTES_CSV, skiprows=2)[["season", "award", "player", "pfr_id", "pos"]]
    for award in POOLS:
        pool = award_pool(table, award)
        sums = pool.groupby("season")[f"target_{award}"].sum()
        print(f"\nin-pool target_{award} ({len(pool) / pool['season'].nunique():.0f} candidates a season):"
              f" sums to 1.0 in {(sums.round(3) >= 1.0).sum()} of {sums.size} seasons, max {sums.max():.3f}")
        missing = targets[targets[f"target_{award}"] > 0].merge(pool[["pfr_id", "season"]], how="left", indicator=True)
        missing = missing[missing["_merge"] == "left_only"].merge(voters[voters["award"] == award], on=["pfr_id", "season"])
        for season, total in sums[sums.round(3) < 1.0].items():
            who = missing[missing["season"] == season]
            names = ", ".join(f"{r.player} ({r.pos}, {getattr(r, f'target_{award}'):.2f})" for r in who.itertuples())
            print(f"  {season}: {total:.3f}  missing: {names}")

    print("\nspot checks (should be the top target_mvp of their season):")
    for season, name in [(2007, "Tom Brady"), (2012, "Adrian Peterson"), (2024, "Josh Allen")]:
        top = award_pool(table, "mvp").query("season == @season").nlargest(1, "target_mvp").iloc[0]
        print(f"  {season} {name}: top is {top['player']} ({top['target_mvp']:.2f})"
              f" {'OK' if top['player'] == name else 'MISMATCH'}")

    now = build_features([2026], through_week=10)
    print(f"\n2026 through week 10: {len(now)} candidates, {now.isna().sum().sum()} missing values,"
          f" by position {now['position_group'].value_counts().to_dict()},"
          + "".join(f" {award} {len(award_pool(now, award))}" for award in POOLS))
    print(now.head(8)[["player", "position_group", "team", "games", "team_win_pct", "yards_pg", "tds_pg", "epa_z"]]
          .to_string(index=False, float_format="%.2f"))


if __name__ == "__main__":
    main()
