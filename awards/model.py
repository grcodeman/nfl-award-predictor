"""The award models: fit on an award's pool from a build_features table, score candidates, turn scores into shares."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# conf_rank (1 = best record in the conference) replaced team_win_pct: voters reward the best team
# in its conference more than the raw record. Leave-one-season-out, it lifted the logistic model's
# top-3 hits at every snapshot week. QB efficiency rates and "led his position" counts were also
# tried and did not help, so they were left out.
OFFENSE = ["yards_z", "tds_z", "epa_z", "turnovers_z", "conf_rank", "availability",
           "is_qb", "is_rb", "is_wr", "is_te"]
# The same recipe for defenders: per-game production z-scored within DL, LB and DB, plus standing and
# games played. DPOY adds last season's DPOY vote, for reputation, and DROY the draft slot. CPOY sets
# this season's production against last season's and how much of last season the player missed. The
# experiments behind each award's set are in the awards/evaluate.py docstring.
DEFENSE = ["sacks_z", "ints_z", "pds_z", "ffs_z", "tackles_z", "def_tds_z", "conf_rank", "availability",
           "is_dl", "is_lb", "is_db"]
FEATURES = {"mvp": OFFENSE, "opoy": OFFENSE, "oroy": OFFENSE, "dpoy": DEFENSE + ["prev_dpoy_vote"],
            "droy": DEFENSE + ["draft_slot"],
            "cpoy": ["prod_z", "prev_prod_z", "prev_availability", "conf_rank", "availability",
                     "is_qb", "is_rb", "is_wr", "is_te", "is_dl", "is_lb", "is_db"],
            # coaches: the team's record, its change from last season, point differential, standing,
            # and whether it's the coach's first season with the team
            "coty": ["team_win_pct", "win_pct_change", "team_pd_pg", "conf_rank", "new_coach"]}

# StandardScaler puts every feature on the same scale, so the regularization treats them evenly.
MODELS = {
    # Regression straight on first-place share. Ridge's penalty keeps weights small, which matters
    # with only 27 seasons of winners to learn from.
    "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    # Classification on "won the award". Its scores are log-odds, softmaxed within the season.
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
}
TARGETS = {"ridge": "target_{award}", "logistic": "won_{award}"}
# Written into the prediction JSON; bump it when features or models change.
# v2 added OPOY, v3 OROY, v4 DPOY, v5 DROY, v6 CPOY, v7 COTY.
MODEL_VERSION = "v7"


def fit(kind, train, award="mvp"):
    """Fit on `train`, which should be the award's own pool (features.award_pool)."""
    model = MODELS[kind]()
    model.fit(train[FEATURES[award]], train[TARGETS[kind].format(award=award)])
    return model


def score(kind, model, table):
    """Higher means more likely to win. Only the order matters for picking a winner."""
    X = table[list(model.feature_names_in_)]  # the columns it was fitted on, so each award uses its own
    return pd.Series(model.predict(X) if kind == "ridge" else model.decision_function(X), index=table.index)


def to_shares(kind, scores, seasons):
    """Turn scores into predicted shares that sum to 1 within each season."""
    if kind == "ridge":
        s = scores.clip(lower=0)  # a share can't be negative
    else:
        s = np.exp(scores - scores.groupby(seasons).transform("max"))  # softmax; subtracting the max avoids overflow
    return s / s.groupby(seasons).transform("sum")
