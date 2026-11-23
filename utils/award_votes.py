"""Turn saved PFR awards pages into one long CSV of AP award voting.

python utils/award_votes.py           parses award-share-data/raw/ into award-share-data/award_votes.csv
python utils/award_votes.py --check   parser self-test

Pages are saved by hand (Chrome: Cmd+S, "Webpage, HTML Only") into award-share-data/raw/;
the season is read from the year in the filename. PFR's Cloudflare check blocks scripted fetching.
"""
import csv
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "award-share-data"
FIELDS = ["season", "award", "rank", "player", "pfr_id", "pos", "team", "votes", "first_place", "share", "voting_system"]
# order matters: rookie before player, so "offensive rookie" isn't read as opoy
AWARDS = [("oroy", "offensive rookie"), ("droy", "defensive rookie"), ("cpoy", "comeback"),
          ("opoy", "offensive player"), ("dpoy", "defensive player"), ("coty", "coach of the year"), ("mvp", "mvp")]
ID_RE = re.compile(r"/(?:players/[A-Z]|coaches)/([^/]+)\.htm")
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.S)


class Tables(HTMLParser):
    """Collects every table as {id, caption, header, rows}; each cell is (text, first link href)."""

    def __init__(self):
        super().__init__()
        self.tables, self.t, self.row, self.cell = [], None, None, None
        self.in_caption = self.in_thead = self.skip = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.t = {"id": a.get("id") or "", "caption": "", "header": [], "rows": []}
        elif self.t is None:
            return
        elif tag == "caption":
            self.in_caption = True
        elif tag == "thead":
            self.in_thead = True
        elif tag == "tr":
            self.row, self.skip = [], "thead" in (a.get("class") or "")  # PFR repeats header rows mid-table
        elif tag in ("th", "td") and self.row is not None:
            self.cell = ["", None]
        elif tag == "a" and self.cell is not None and self.cell[1] is None:
            self.cell[1] = a.get("href")

    def handle_endtag(self, tag):
        if self.t is None:
            return
        if tag == "caption":
            self.in_caption = False
        elif tag == "thead":
            self.in_thead = False
        elif tag in ("th", "td") and self.cell is not None:
            self.row.append((self.cell[0].strip(), self.cell[1]))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.in_thead:
                self.t["header"] = [text for text, _ in self.row]  # last header row has the real column names
            elif not self.skip and self.row:
                self.t["rows"].append(self.row)
            self.row = None
        elif tag == "table":
            self.tables.append(self.t)
            self.t = None

    def handle_data(self, data):
        if self.cell is not None:
            self.cell[0] += data
        elif self.in_caption:
            self.t["caption"] += data


def award_for(table):
    text = f"{table['id']} {table['caption']}".lower()
    if "assistant" in text:
        return None
    return next((award for award, key in AWARDS if key in text), None)


def parse(html, season):
    p = Tables()
    # PFR hides some tables inside HTML comments: unwrap those, drop the rest (IE conditional comments break the parser)
    p.feed(COMMENT_RE.sub(lambda m: m.group(1) if "<table" in m.group(1) else "", html))
    out = []
    for t in p.tables:
        if "Share" not in t["header"]:  # only voting tables have a Share column
            continue
        award = award_for(t)
        if not award:
            print(f"{season}: skipped voting table id={t['id']!r} caption={t['caption']!r}", file=sys.stderr)
            continue
        col = {h: i for i, h in enumerate(t["header"])}
        for row in t["rows"]:
            def cell(*names):
                return next((row[col[n]] for n in names if n in col and col[n] < len(row)), ("", None))

            name, href = cell("Player", "Coach")
            if not name:
                continue
            m = ID_RE.search(href or "")
            share = cell("Share")[0].rstrip("%")
            out.append({
                "season": season, "award": award, "rank": cell("Rk")[0], "player": name,
                "pfr_id": m.group(1) if m else "", "pos": cell("Pos")[0], "team": cell("Tm")[0],
                "votes": cell("Vote Pts", "Votes")[0], "first_place": cell("1st Place")[0],
                "share": round(float(share) / 100, 4) if share else "",
                "voting_system": "single_vote" if season <= 2021 else "ranked_points",
            })
    return out


def main():
    rows, seen = [], set()
    for f in sorted((DATA / "raw").glob("*.htm*")):
        season = int(re.search(r"(?:19|20)\d\d", f.name).group())
        found = parse(f.read_text(encoding="utf-8", errors="replace"), season)
        print(f"{season}: {len(found)} rows, awards: {sorted({r['award'] for r in found})}")
        rows += found
        seen.add(season)
    if missing := sorted(set(range(1999, 2026)) - seen):
        print(f"no saved page for: {missing}")
    if not rows:
        return
    out = DATA / "award_votes.csv"
    with out.open("w", newline="") as fh:
        fh.write(f"--- pulled from https://www.pro-football-reference.com/awards/awards_YYYY.htm ({min(seen)}-{max(seen)})\n\n")
        w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


def check():
    """Fake page: IE comment, commented-out table, repeated header row, rookie-vs-player naming, assistant coach skipped."""
    head = "<thead><tr><th>Rk</th><th>Player</th><th>Share</th></tr></thead>"
    html = (
        '<!--[if lt IE 9]><script src="x.js"></script><![endif]-->'  # real PFR header comment; broke naive uncommenting
        f'<table id="a"><caption>AP Offensive Player of the Year</caption>{head}<tbody>'
        '<tr><th>1</th><td><a href="/players/A/AlleJo02.htm">Josh Allen</a></td><td>73.2%</td></tr></tbody></table>'
        f'<!--<table id="b"><caption>AP Offensive Rookie of the Year</caption>{head}<tbody>'
        '<tr class="thead"><th>Rk</th><th>Player</th><th>Share</th></tr>'
        '<tr><th>1</th><td><a href="/players/R/RobiBi01.htm">Bijan Robinson</a></td><td>10%</td></tr></tbody></table>-->'
        f'<table id="c"><caption>AP Assistant Coach of the Year</caption>{head}<tbody>'
        '<tr><th>1</th><td>Someone</td><td>5%</td></tr></tbody></table>'
    )
    got = [(r["award"], r["pfr_id"], r["share"], r["voting_system"]) for r in parse(html, 2021)]
    assert got == [("opoy", "AlleJo02", 0.732, "single_vote"), ("oroy", "RobiBi01", 0.1, "single_vote")], got
    assert parse(html, 2022)[0]["voting_system"] == "ranked_points"
    print("check ok")


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        main()
