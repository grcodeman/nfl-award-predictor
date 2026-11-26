# nfl-award-predictor
playing around with nfl stats to predict nfl awards such as: mvp, opoty, etc, and now game picks too

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Layout
- `predictor/data.py`: loaders shared by everything: the nflverse cache, schedules (with kickoff times) and team records
- `predictor/models.py`: every model's name, version and changelog
- `predictor/awards/`: the AP award models (features, model, evaluation, weekly prediction)
- `predictor/games/`: game picks: the Elo model, the pick ledger and grading, and the backtest
- `predictions/`: everything the dashboard reads; `predictions/games/` holds the pick ledger
- `site/`: the static dashboard

## Run
```bash
python -m predictor.games                     # grade finished games, write next week's picks if due
python -m predictor.games backtest            # rewrite each game model's 2015-2025 backtest
python -m predictor.awards.predict            # award predictions for the latest completed week
python -m predictor.awards.evaluate dpoy      # leave-one-season-out evaluation of one award
```
The weekly GitHub Action runs the first and third every Monday to Wednesday morning.

Game picks for a week are written once, before its first kickoff, and never rewritten (the code refuses).
Backtests are replays, kept apart in `predictions/games/backtest/` and labeled `"kind": "backtest"`.

Add a package: `pip install <pkg>`, then add it to `requirements.txt`.
Leave the venv: `deactivate`
