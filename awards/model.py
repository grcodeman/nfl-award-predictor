"""The two MVP models: fit on a build_features table, score candidates, turn scores into shares."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

# conf_rank (1 = best record in the conference) replaced team_win_pct: voters reward the best team
# in its conference more than the raw record. Leave-one-season-out, it lifted the logistic model's
# top-3 hits at every snapshot week. QB efficiency rates and "led his position" counts were also
# tried and did not help, so they were left out.
FEATURES = ["yards_z", "tds_z", "epa_z", "turnovers_z", "conf_rank", "availability",
            "is_qb", "is_rb", "is_wr", "is_te"]

# StandardScaler puts every feature on the same scale, so the regularization treats them evenly.
MODELS = {
    # Regression straight on first-place share. Ridge's penalty keeps weights small, which matters
    # with only 27 seasons of winners to learn from.
    "ridge": lambda: make_pipeline(StandardScaler(), Ridge(alpha=1.0)),
    # Classification on "won the award". Its scores are log-odds, softmaxed within the season.
    "logistic": lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)),
}
TARGETS = {"ridge": "target_{award}", "logistic": "won_{award}"}


def fit(kind, train, award="mvp"):
    model = MODELS[kind]()
    model.fit(train[FEATURES], train[TARGETS[kind].format(award=award)])
    return model


def score(kind, model, table):
    """Higher means more likely to win. Only the order matters for picking a winner."""
    X = table[FEATURES]
    return pd.Series(model.predict(X) if kind == "ridge" else model.decision_function(X), index=table.index)


def to_shares(kind, scores, seasons):
    """Turn scores into predicted shares that sum to 1 within each season."""
    if kind == "ridge":
        s = scores.clip(lower=0)  # a share can't be negative
    else:
        s = np.exp(scores - scores.groupby(seasons).transform("max"))  # softmax; subtracting the max avoids overflow
    return s / s.groupby(seasons).transform("sum")
