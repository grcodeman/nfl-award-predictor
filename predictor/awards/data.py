"""Award loaders: AP votes and vote targets, the player id crosswalk, weekly player stats, and head coach
photos. Schedules and team records are shared with the game models, in predictor/data.py."""
import html
import json
import re
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import nflreadpy as nfl
import pandas as pd

from predictor.data import OLD_TEAM_CODES, ROOT

VOTES_CSV = ROOT / "award-share-data" / "award_votes.csv"

ID_COLS = ["season", "week", "game_id", "player_id", "player_display_name", "position", "position_group", "team",
           "headshot_url"]
STAT_COLS = [
    "attempts", "carries", "receptions",
    "passing_yards", "rushing_yards", "receiving_yards",
    "passing_tds", "rushing_tds", "receiving_tds",
    "passing_epa", "rushing_epa", "receiving_epa",
    "passing_interceptions", "sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost",
    # Defense: the columns recorded the same way every season since 1999. Tackles for loss are blank
    # 2003-2011 and QB hits 2003-2005, and assisted tackles changed meaning in 2025, so those are out.
    "def_sacks", "def_interceptions", "def_pass_defended", "def_fumbles_forced", "def_tackles_solo", "def_tds",
]


def team_code(name):
    """A full team name from the award files ("St. Louis Rams") -> today's code ("LA"), by nickname."""
    nick = name.split()[-1]
    return {"Redskins": "WAS", "Team": "WAS", "Commanders": "WAS"}.get(nick) or _NICKNAMES[nick]


_NICKNAMES = None


def coach_id(team):
    """COTY candidates are team-seasons, so a coach's key is his team's: the AP's 2012 winner, Bruce
    Arians, coached the Colts while Chuck Pagano was ill, and the schedules list Pagano all season."""
    return f"HC-{team}"


def load_votes():
    """The vote file, with COTY rows keyed by coach_id instead of the coach's own PFR id."""
    global _NICKNAMES
    if _NICKNAMES is None:
        teams = nfl.load_teams().to_pandas()
        teams = teams[~teams["team_abbr"].isin([*OLD_TEAM_CODES, "LAR"])]  # one code per nickname, today's
        _NICKNAMES = dict(zip(teams["team_nick"], teams["team_abbr"]))
    v = pd.read_csv(VOTES_CSV, skiprows=2)
    coty = v["award"] == "coty"
    v.loc[coty, "pfr_id"] = v.loc[coty, "team"].map(lambda name: coach_id(team_code(name)))
    return v


def load_targets(awards=("mvp", "opoy", "oroy", "dpoy", "droy", "cpoy", "coty")):
    """One row per candidate-season that got votes: pfr_id, season, target_* and won_* for each award.

    target_* is first-place share. Unlike `share`, it sums to 1.0 within every season and award,
    so it means the same thing before and after the 2022 switch to ranked ballots.
    won_* is 1 for the winner, from the award-data/ winner files, which list both 2003 co-MVPs.
    """
    v = load_votes()
    v = v[v["award"].isin(awards)].dropna(subset=["pfr_id"])  # drops Denny Kellington, a team trainer (2022 MVP)
    first = v["first_place"].fillna(0)
    total_first = first.groupby([v["season"], v["award"]]).transform("sum")
    # single_vote seasons: every vote was a first-place vote, so share already is first-place share
    v["target"] = v["share"].where(v["voting_system"] == "single_vote", first / total_first)
    wide = v.pivot_table(index=["pfr_id", "season"], columns="award", values="target", aggfunc="sum", fill_value=0)
    wide = wide.add_prefix("target_").reset_index().rename_axis(columns=None)
    for award in awards:
        w = pd.read_csv(ROOT / "award-data" / f"{award}.csv", skiprows=2)
        if award == "coty":  # the coach file has no id column; it starts in 1957, before some team names
            w = w[w["Year"] >= 1999].assign(**{"Player-additional": lambda d: d["Tm"].map(team_code).map(coach_id)})
        winners = set(zip(w["Player-additional"], w["Year"]))
        wide[f"won_{award}"] = [int(key in winners) for key in zip(wide["pfr_id"], wide["season"])]
    return wide


def add_targets(table):
    """Attach target_* and won_* to a build_features table; 0 for players who got no votes."""
    t = table.merge(load_targets(), on=["pfr_id", "season"], how="left", validate="many_to_one")
    cols = [c for c in t.columns if c.startswith(("target_", "won_"))]
    t[cols] = t[cols].fillna(0)
    return t


def load_player_ids():
    """player_id (the gsis id used in nflverse stats) -> pfr_id (Pro Football Reference, used in the vote file),
    rookie_season and draft_pick (overall, blank if undrafted).

    rookie_season is filled in for every candidate back to 1999 and matches all 233 OROY and DROY
    vote-getters. draft_year is blank for undrafted rookies (Phillip Lindsay 2018), so it isn't used.
    """
    players = nfl.load_players().to_pandas()
    return players[["gsis_id", "pfr_id", "rookie_season", "draft_pick"]].rename(columns={"gsis_id": "player_id"})


def load_weekly_stats(seasons, through_week):
    """Regular-season player stats, one row per player per game, weeks 1 through `through_week`."""
    s = nfl.load_player_stats(list(seasons), summary_level="week").to_pandas()
    # one 1999 row (Steve Bono, week 9) has no team; it can't be matched to a team record
    s = s[(s["season_type"] == "REG") & (s["week"] <= through_week) & s["player_id"].notna() & s["team"].notna()]
    return s[ID_COLS + STAT_COLS].fillna({c: 0 for c in STAT_COLS})  # EPA is blank when a player had no such plays


# Head coach photos. nflverse has none, so they come from each coach's Wikipedia page: its lead image,
# where the page has a free one. Wikimedia asks API clients to send a descriptive User-Agent.
WIKI_API = "https://en.wikipedia.org/w/api.php"
WIKI_UA = "nfl-coach-photos/1.0 (weekly award predictions; python urllib)"


def _wiki(**params):
    """One API call. A rate limit (HTTP 429) raises straight away rather than retrying: photos are
    optional, and the next weekly run asks again."""
    url = f"{WIKI_API}?{urlencode({'format': 'json', 'formatversion': 2, **params})}"
    with urlopen(Request(url, headers={"User-Agent": WIKI_UA}), timeout=30) as r:
        return json.load(r)


def _wiki_pages(titles, **params):
    """Each title asked for -> its page (after normalizing and following redirects), 50 titles a request."""
    out = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        q = _wiki(action="query", titles="|".join(chunk), redirects=1, **params)["query"]
        hop = {h["from"]: h["to"] for h in q.get("normalized", []) + q.get("redirects", [])}
        pages = {p["title"]: p for p in q.get("pages", [])}
        for t in chunk:
            out[t] = pages.get(hop.get(hop.get(t, t), hop.get(t, t)), {})
    return out


def coach_photos(names):
    """Coach name -> {"url", "page", "credit"} for coaches whose Wikipedia page has a free lead photo.

    A page counts only if its short description mentions football, so a namesake can't stand in
    ("Mike Smith" is several people). The disambiguated titles are tried first. credit is the photo's
    author and license, which CC BY-SA photos require to be shown.
    """
    found = {}
    for suffix in [" (American football coach)", " (American football)", ""]:
        todo = [n for n in sorted(set(names)) if n not in found]
        pages = _wiki_pages([n + suffix for n in todo], prop="pageimages|description",
                            piprop="thumbnail|name", pithumbsize=400)
        for n in todo:
            p = pages[n + suffix]
            if p and not p.get("missing") and "football" in p.get("description", "").lower():
                found[n] = p  # the coach's page, with or without a photo
    with_photo = {n: p for n, p in found.items() if p.get("thumbnail") and p.get("pageimage")}
    files = _wiki_pages([f"File:{p['pageimage']}" for p in with_photo.values()], prop="imageinfo",
                        iiprop="extmetadata", iiextmetadatafilter="Artist|LicenseShortName")
    out = {}
    for n, p in with_photo.items():
        meta = ((files[f"File:{p['pageimage']}"].get("imageinfo") or [{}])[0]).get("extmetadata", {})
        artist = html.unescape(re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value", ""))).strip()
        license_ = meta.get("LicenseShortName", {}).get("value", "")
        out[n] = {
            "url": p["thumbnail"]["source"].split("?")[0],
            "page": f"https://en.wikipedia.org/wiki/{quote(p['title'].replace(' ', '_'))}",
            "credit": ", ".join(x for x in [artist, license_] if x) or "Wikimedia Commons",
        }
    return out
