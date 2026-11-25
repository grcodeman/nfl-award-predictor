---
name: add-award
description: Use when adding another NFL award (oroy, dpoy, droy, cpoy, coty) to the predictor, end to end. Covers the data checks, the model and its evaluation floor, the weekly prediction JSON, and the dashboard tab, following the same baseline approach used for MVP and OPOY.
argument-hint: <award code, e.g. oroy>
---

# Add an award

This is the process OPOY went through (Phase 6), written down so every award gets the same baseline. One award per session. Stop after each numbered step that has checks, show them, and wait for a go-ahead before publishing.

## Where an award touches the system

| Piece | File | What changes |
|---|---|---|
| Vote targets and won labels | `awards/data.py` `load_targets(awards=...)` | add the code to the default tuple |
| Pool coverage check | `awards/features.py` `main()` | add the code to the `for award in [...]` list |
| Candidate pool and features | `awards/features.py` `build_features()` | only for awards the offensive pool doesn't cover (see step 0) |
| Model | `awards/model.py` | usually nothing; `FEATURES` is shared |
| Evaluation floor | `awards/evaluate.py` `FLOOR` | add `FLOOR[award]` |
| Weekly JSON | `awards/predict.py` `AWARDS`, `awards/model.py` `MODEL_VERSION` | add the code, bump the version |
| Dashboard tab | `site/app.js` `AWARD_NAMES` | add `{ short, full }` |

The set is these seven: mvp, opoy, dpoy, oroy, droy, cpoy and coty. The data side is already there: `award-share-data/award_votes.csv` has 27 seasons of votes for each, and `award-data/<award>.csv` has the winners (co-winners included).

## Step 0: classify the award

Decide which path it takes before writing code.

| Award | Path | What it needs beyond what exists |
|---|---|---|
| oroy | **A** with a filter | the current offensive pool (QB, RB, WR, TE), limited to rookies: `nfl.load_players()` has `rookie_season` and `draft_year`. Check that they're filled in for 1999-era players before trusting them. The workload thresholds may need lowering for rookies; let the coverage check decide. |
| dpoy | **B** | a defensive candidate pool (`position_group` DL, LB, DB) and defensive features from the `def_*` stat columns (`def_sacks`, `def_qb_hits`, `def_tackles_for_loss`, `def_interceptions`, `def_pass_defended`, `def_fumbles_forced`, `def_tds`), z-scored within DL, LB and DB |
| droy | **B** with a filter | the dpoy work plus the rookie filter |
| cpoy | **B** | features from the previous season (games missed, drop in production), since the award is about coming back |
| coty | **C** | coaches, not players: no player rows, and the winner file has no player id column. It needs a team-level table (win pct change, point differential). Stop and propose a design to the user. |

- **A** goes straight to step 1.
- **B** extends `build_features` first (see "Path B" below), then follows steps 1 to 6.
- **C** stops here and talks it through with the user.

## Step 1: wire the label and check pool coverage

1. Add the code to `load_targets(awards=(...))` in `awards/data.py` and to the check loop in `features.main()`.
2. Run `python -m awards.features`.
3. Read `in-pool target_<award>`. In-pool first-place share should sum to about 1.0 in most seasons. It never goes above 1.0 except for rounding.
   - A few misses, like J.J. Watt in MVP 2014, are fine. List them.
   - If many seasons fall well short, the pool doesn't fit the award: go back to step 0 and treat it as path B.

**Check:** in-pool sums, plus who's missing and why.

## Step 2: baseline evaluation

1. Add `FLOOR[award]`.
   - **If the plan gives a floor,** use it.
   - **If not,** run the baseline first and record its numbers as the floor. Say in the docstring that the floor came from the baseline.
2. Run `python -m awards.evaluate <award>` with the shared `FEATURES` unchanged.
3. Read every row, not just the full season. The dashboard is read mid-season, so weeks 8, 11 and 14 matter.

**Check:** the evaluation table, the misses, and whether it clears the floor.

## Step 3: a few feature experiments, decided in advance

- Write down at most five feature sets before running them, each with a reason (for example "team standing matters less for an offensive award"). Don't search until something wins: with 27 seasons, a difference of one or two seasons is noise.
- Use a scratch script in the session's scratchpad, not the repo. Build the snapshots once with `add_targets(build_features(SEASONS, week))`, set `awards.model.FEATURES`, and rerun the leave-one-season-out loop from `awards/evaluate.py:run`.
- **Keep the shared set** unless another set does better at weeks 11 and 14 *and* at full season without losing elsewhere. OPOY kept the shared set: swapping `conf_rank` for `team_win_pct` won at full season (18/24) but lost badly at weeks 8 and 11.
- If an award really needs its own features:
  1. Turn `FEATURES` into a dict keyed by award.
  2. Make `score()` read the columns the model was fitted on (`list(model.feature_names_in_)`; the pipeline has it when it's fitted on a DataFrame). Check that this attribute exists before relying on it.
  3. Rerun MVP and OPOY to confirm their tables didn't move.
- Record the decision and the numbers behind it in the `evaluate.py` docstring.

**Check:** the experiment table and the decision.

## Step 4: publish to the weekly JSON

1. Add the code to `AWARDS` in `awards/predict.py` and bump `MODEL_VERSION` in `awards/model.py`. Adding a key to the JSON is a deliberate contract change.
2. Rebuild the current season so the new tab has a trend from week 1:
   ```bash
   for w in $(seq 1 <latest>); do python -m awards.predict --season <season> --week $w; done
   ```
   The local nflreadpy cache is up to a day old, so `latest` here can trail by a week. The GitHub Action downloads fresh data, so its next run picks up the newest week with the award included.
3. **Check:**
   - every week file has the award with 10 rows
   - the top-10 shares sum to just under 1.0
   - `prev_rank` and `prev_share` are null in week 1
   - the existing awards' numbers are unchanged from before

## Step 5: dashboard tab

1. Add `AWARD_NAMES[award] = { short, full }` in `site/app.js`, copied from this table, so every tab reads the same way:

   | code | short | full |
   |---|---|---|
   | mvp | MVP | Most Valuable Player |
   | opoy | OPOY | Offensive Player of the Year |
   | dpoy | DPOY | Defensive Player of the Year |
   | oroy | OROY | Offensive Rookie of the Year |
   | droy | DROY | Defensive Rookie of the Year |
   | cpoy | CPOY | Comeback Player of the Year |
   | coty | COTY | Coach of the Year |

   The naming rule:
   - **`short`** (the acronym) goes in compact spots: the tab, the heading ("DPOY race") and the browser title ("Award Watch: NFL DPOY race").
   - **`full`** (the AP's name, spelled out) goes in sentences: the lede ("…share of the AP Defensive Player of the Year vote…") and the empty-week message.
   - Never put an acronym in `full`.
   - Every other string stays award-neutral. A new sentence that needs the award's name takes it from `awardName()`, never a literal.
   - MVP is the default tab, so `site/index.html` repeats its title and lede as static text (this avoids a text swap at first paint). Change those only together with MVP's entry.
2. The "How it works" copy in `site/index.html` is static and shared by every tab. It names QB, RB, WR and TE, the offensive features and a pool of about 90. Before the first path B award ships, make it cover every pool, or render one line per award from `app.js`, so no tab describes another award's model.
3. Serve from the repo root (`python -m http.server 8000`) and drive it with Playwright from the scratchpad, in light and dark, at 1440 and 390 wide. **Check:**
   - every section renders for the new tab: ticker, leader card, table, chart, swings, head to head
   - the tab, heading, browser title and lede read the same way as the MVP tab's, with only the award name changed
   - `#<award>` deep-links to the tab, and the arrow keys switch tabs
   - no truncated labels; long surnames are the usual culprit (see "Lead over No. 2" in `renderHero`)
   - the swings text reads correctly for this race and uses no pronouns, because the rows are real people
   - no console errors and no horizontal scroll
4. Run `~/.agents/skills/impeccable/scripts/impeccable detect --json site/index.html site/style.css site/app.js` and expect 0 findings.

## Step 6: wrap up

- Rerun `python -m awards.evaluate mvp` and `opoy`. Their tables must match the ones recorded before this change.
- Commit with the project's naming (for example "add oroy") once the user asks, then push. Wait for GitHub Pages and load the live `…/site/#<award>`.
- Update the project memory note with what was added and its evaluation numbers.

## Path B: extending the pool

Do this before step 1, keeping design rule 1: `build_features` stays the only way features get built.

- **Pool:** add the new candidate pool next to the offensive one, judged per team game so it works mid-season (for example, defenders with enough snaps or tackles per team game). Size it like the offensive pool, roughly 100 per season, then check coverage in step 1.
- **Features:** z-score the new features within their own groups (DL, LB, DB) and set them to 0 for players they don't apply to. Add position flags for the new groups.
- **Training pool per award:** `fit()` should train only on rows from the award's own pool. A defender should never be a candidate for an offensive award, and the other way round.
- **Existing awards stay put:** rerun `python -m awards.features`, then `python -m awards.evaluate` for mvp and opoy. Their pools and tables must be unchanged.

## Gotchas already paid for

- **Read the vote CSVs with `skiprows=2`:** every CSV starts with a `--- pulled from` line and a blank line.
- **The target is first-place share, not `share`:** from 2022 on, ballots are ranked, and `share` sums to more than 1.
- **Co-winners:** the `won_<award>` labels come from `award-data/<award>.csv`, because the vote file can't mark co-winners (2003 MVP).
- **Never fetch Pro Football Reference pages from code:** Cloudflare blocks it. The raw pages are saved by hand into `award-share-data/raw/`, and `python utils/award_votes.py` rebuilds the vote CSV.
- **Python's test server can drop a connection mid-load:** the page then shows its "didn't load" fallback. Recapture before treating it as a bug.
- **The weekly Action skips a week that already has a file:** to rebuild a past week after a change, run `predict --week N` locally, or trigger the workflow with the `week` input.
