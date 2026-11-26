"""Every model that publishes numbers: its name, its current version, and one line per version saying
what changed.

A version goes up with any change that could move a published number: features, candidate pools,
parameters, training rules. Pick files, grades and award files record the name and version that made
them, so every number traces back to the model behind it. Award files from before per-model versions
(2026 weeks 1-11) say "model_version": "v7" instead; each award's version 1 is the model they used.

Game models: the champion (CHAMPION in predictor/games/__init__.py) feeds the dashboard, and every
other model there is a challenger that logs picks into the same ledger without being shown. A
challenger replaces the champion only by a promotion rule written into its first changelog line before
its backtest runs, for example: lower log loss than the champion over the 2015-2025 backtest, and no
worse in weeks 1-4.
"""
CHANGELOG = {
    "games-elo": {
        1: "Elo with a margin-of-victory multiplier: K 20, home edge 55 (none at neutral sites), 45% pull"
           " back to 1500 each offseason, picked on 2002-2014.",
    },
    "mvp": {
        1: "Logistic on per-team-game yards, TDs, EPA and turnovers (z within position), conference rank,"
           " games played and position, over starting QBs, RBs, WRs and TEs.",
    },
    "opoy": {1: "The MVP model, trained on OPOY winners."},
    "oroy": {1: "The MVP features, over rookies with a regular role."},
    "dpoy": {
        1: "Logistic on per-team-game sacks, INTs, passes defended, forced fumbles, solo tackles and"
           " defensive TDs (z within DL, LB and DB), conference rank, games played, position and last"
           " season's DPOY vote.",
    },
    "droy": {1: "The DPOY features with draft slot in place of last season's vote, over defensive rookies."},
    "cpoy": {
        1: "Logistic on this season's and last season's production, last season's games played,"
           " conference rank, games played and position, over non-rookies on either side.",
    },
    "coty": {
        1: "Logistic on the team's win pct, its change from last season, point differential, conference"
           " rank and whether it's the coach's first season with the team.",
    },
}


def version(name):
    """The current version of a model."""
    return max(CHANGELOG[name])
