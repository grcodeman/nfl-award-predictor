// Award Watch: reads the JSON in ../predictions/ and renders every part of the page from it.
"use strict";

const DATA = "../predictions/";
// short: tab and page heading; full: the description and the browser title
const AWARD_NAMES = {
  mvp: { short: "MVP", full: "Most Valuable Player" },
  opoy: { short: "OPOY", full: "Offensive Player of the Year" },
  oroy: { short: "OROY", full: "Offensive Rookie of the Year" },
  dpoy: { short: "DPOY", full: "Defensive Player of the Year", stats: "defense" },
  droy: { short: "DROY", full: "Defensive Rookie of the Year", stats: "defense" },
  cpoy: { short: "CPOY", full: "Comeback Player of the Year", stats: "comeback" },
};
const awardName = (award) => AWARD_NAMES[award] || { short: award.toUpperCase(), full: award.toUpperCase() };
// The four stats an award's leader card, table and head to head show, keyed to the JSON's stats.
// unit: the inline label on phones ("92.4 yds/g"); long: the head-to-head label; lower: fewer is better;
// neutral: neither side is better, so the head to head doesn't bold it.
const STAT_SETS = {
  offense: [
    { key: "yards_per_game", label: "Yds/g", unit: "yds/g", digits: 1 },
    { key: "tds", label: "TD", unit: "TD" },
    { key: "turnovers", label: "TO", long: "Turnovers", unit: "TO", lower: true },
    { key: "epa_per_game", label: "EPA/g", unit: "EPA/g", digits: 1 },
  ],
  defense: [
    { key: "sacks", label: "Sacks", unit: "sacks" },
    { key: "ints", label: "INT", unit: "INT" },
    { key: "passes_defended", label: "PD", long: "Passes defended", unit: "PD" },
    { key: "tackles", label: "Solo", long: "Solo tackles", unit: "solo tkl" },
  ],
  // CPOY mixes offense and defense, so production is a percentile of the starters at the position.
  // Labels stay six characters or fewer so they fit a 360px phone's leader card.
  comeback: [
    { key: "prev_games", label: "Prev G", long: "Games last season", unit: "G last yr", neutral: true },
    { key: "prev_prod_pct", label: "Prev %", long: "Percentile last season", unit: "% last yr", neutral: true },
    { key: "games", label: "G", long: "Games", unit: "G" },
    { key: "prod_pct", label: "%", long: "Percentile", unit: "%" },
  ],
};
const statSet = (award) => STAT_SETS[AWARD_NAMES[award]?.stats || "offense"];
// digits fixes the decimals; otherwise whole numbers stay whole and half sacks show as 4.5
const showStat = (st, r) => { const x = r.stats[st.key]; return st.digits ? x.toFixed(st.digits) : String(x); };
// "How it works", one per award, because each award ranks its own pool. MVP's is also static in index.html.
const RETRAINED = "Each week a logistic regression is retrained on AP voting from 1999 to 2025 and scores";
const OFFENSE = "per-game yards, touchdowns, EPA and turnovers, the team's conference standing, and games played";
const shares = (pool, who = "player") =>
  `Shares add up to 100% across the whole pool of ${pool}, so they read as each ${who}'s slice of the vote if the season ended today.`;
const STARTERS_HOW = `${RETRAINED} every starting-caliber QB, RB, WR and TE on ${OFFENSE}. ${shares("about 90 players")}`;
const HOW_IT_WORKS = {
  mvp: STARTERS_HOW,
  opoy: STARTERS_HOW,
  oroy: `${RETRAINED} every rookie QB, RB, WR and TE with a regular role, compared with the league's starters, on ${OFFENSE}. ${shares("about 20 rookies")}`,
  dpoy: `${RETRAINED} every starting defensive lineman, linebacker and defensive back on per-game sacks, interceptions, passes defended, forced fumbles, solo tackles and defensive touchdowns, the team's conference standing, games played, and last season's DPOY votes. ${shares("about 200 players")}`,
  droy: `${RETRAINED} every rookie defensive lineman, linebacker and defensive back with a regular role, compared with the league's starters, on per-game sacks, interceptions, passes defended, forced fumbles, solo tackles and defensive touchdowns, the team's conference standing, games played, and draft position. ${shares("about 30 rookies")}`,
  cpoy: `Each week a logistic regression is retrained on AP voting from 2000 to 2025 and scores every non-rookie with a regular role, on offense or defense, on this season's production and last season's, the share of last season's games played, the team's conference standing, and games played. % is production as a percentile of the starters at the same position: 88 means ahead of 88% of them. ${shares("about 450 players")}`,
};
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5"]; // chart colors, fixed order; color follows the player, not the rank
const NIGHT = ["--n1", "--n2", "--n3", "--n4", "--n5"]; // the same hues stepped for the dark leader card
const SVG_NS = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);
const pct = (x) => `${(x * 100).toFixed(1)}%`;
const pts = (x) => Math.abs(x * 100).toFixed(1); // a share difference, in percentage points
const ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"];
const NUMBERS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];
const suffix = (n) => (n % 100 >= 11 && n % 100 <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] || "th");
const ordinalNum = (n) => `${n}${suffix(n)}`;
const ordinal = (n) => ORDINALS[n - 1] || ordinalNum(n);
// Two ranks in one phrase share a style: "fourth to ninth", but "17th to 8th", never "17th to eighth".
const ordinalPair = (a, b) => (a > 10 || b > 10 ? [ordinalNum(a), ordinalNum(b)] : [ordinal(a), ordinal(b)]);
const numberWord = (n) => NUMBERS[n] || String(n);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

// DOM helpers. Text always goes in through textContent: names come from data files.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "vars") for (const [name, v] of Object.entries(value)) node.style.setProperty(name, v);
    else node.setAttribute(key, value);
  }
  node.append(...children.filter((c) => c != null));
  return node;
}
function svgEl(tag, attrs = {}, style = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  Object.assign(node.style, style);
  return node;
}
function icon(kind) {
  const paths = { up: "M5 1.5 9.5 8.5H.5z", down: "M5 8.5 .5 1.5h9z", asc: "M5 2 9 8H1z", desc: "M5 8 1 2h8z" };
  const s = svgEl("svg", { viewBox: "0 0 10 10", "aria-hidden": "true" });
  s.append(svgEl("path", { d: paths[kind], fill: "currentColor" }));
  return s;
}
function lastName(name) {
  const parts = name.split(" ").filter((p) => !/^(Jr\.?|Sr\.?)$/.test(p));
  const n = parts.length;
  if (n > 2 && /^(II|III|IV|V)$/.test(parts[n - 1])) return `${parts[n - 2]} ${parts[n - 1]}`;
  return n > 2 && parts[n - 2] === "St." ? `St. ${parts[n - 1]}` : parts[n - 1];
}
function initials(name) {
  return name.split(" ").filter(Boolean).map((p) => p[0]).slice(0, 2).join("");
}
function winPct(record) {
  const [w, l, t = 0] = record.split("-").map(Number);
  return (w + t / 2) / Math.max(w + l + t, 1);
}
// NFL headshots are multi-megabyte originals. Their image CDN resizes on request, so ask for a face
// crop at 2x the displayed size; a URL in any other shape is used as is.
function headshot(url, px) {
  return url.replace("/image/upload/f_auto,q_auto/", `/image/upload/f_auto,q_auto,c_thumb,g_face,w_${px},h_${px}/`);
}
function avatar(row, cls, px) {
  const box = el("div", { class: cls });
  if (row.headshot_url) {
    const img = el("img", { src: headshot(row.headshot_url, px), alt: "", decoding: "async" });
    img.addEventListener("error", () => img.replaceWith(el("span", { class: "initials", text: initials(row.player) })), { once: true });
    box.append(img);
  } else {
    box.append(el("span", { class: "initials", "aria-hidden": "true", text: initials(row.player) }));
  }
  return box;
}

// A movement marker: arrow plus amount, with a sentence for screen readers.
function move(delta, { unit = "", digits = 1, words = "" } = {}) {
  if (delta == null) return el("span", { class: "move flat", text: "New" });
  const shown = digits ? Math.abs(delta).toFixed(digits) : String(Math.abs(delta));
  if (Number(shown) === 0) {
    return el("span", { class: "move flat" }, el("span", { "aria-hidden": "true", text: "–" }), el("span", { class: "visually-hidden", text: "No change" }));
  }
  const kind = delta > 0 ? "up" : "down";
  return el("span", { class: `move ${kind}` }, icon(kind), el("span", { "aria-hidden": "true", text: `${shown}${unit}` }),
    el("span", { class: "visually-hidden", text: `${kind === "up" ? "Up" : "Down"} ${shown}${words}` }));
}
const shareChange = (r) => (r.prev_share == null ? null : r.share - r.prev_share);
const rankChange = (r) => (r.prev_rank == null ? null : r.prev_rank - r.rank);

async function getJSON(path) {
  const res = await fetch(DATA + path, { cache: "no-cache" });
  if (!res.ok) throw Object.assign(new Error(`${path}: HTTP ${res.status}`), { status: res.status });
  return res.json();
}

function showMessage(text) {
  $("content").hidden = true;
  $("ticker-bar").hidden = true;
  $("message").hidden = false;
  $("message").textContent = text;
  $("lede").textContent = "";
  $("panel").setAttribute("aria-busy", "false");
}

async function main() {
  let index, latest, teams;
  try {
    [index, latest, teams] = await Promise.all([getJSON("index.json"), getJSON("latest.json"), getJSON("teams.json")]);
  } catch (err) {
    console.error(err);
    showMessage(err.status === 404
      ? "No predictions yet. The first update lands the Tuesday after week 1."
      : "Couldn't load the predictions. Check your connection, then refresh the page.");
    return;
  }

  const updated = new Date(latest.generated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  $("status").replaceChildren(
    el("span", { class: "status-week", text: `${latest.season} season · Through week ${latest.through_week}` }),
    el("span", { class: "sep", "aria-hidden": "true", text: " · " }),
    el("span", { class: "status-updated", text: `Updated ${updated}` }));

  // The chart and the streaks need every week of the season. If those fail, the rest still renders.
  let weeks = [];
  try {
    const weekNumbers = index.seasons[String(latest.season)] || [];
    weeks = await Promise.all(weekNumbers.map((w) => getJSON(`${latest.season}/week_${String(w).padStart(2, "0")}.json`)));
  } catch (err) {
    console.error(err);
  }

  const awards = Object.keys(latest.awards);
  const tabs = awards.map((award) => el("button", {
    class: "tab", role: "tab", id: `tab-${award}`, "aria-controls": "panel", type: "button",
    text: awardName(award).short,
  }));
  $("tabs").replaceChildren(...tabs);
  const strip = $("tabs");
  const edges = () => {
    strip.classList.toggle("more-left", strip.scrollLeft > 1);
    strip.classList.toggle("more-right", strip.scrollLeft + strip.clientWidth < strip.scrollWidth - 1);
  };
  strip.addEventListener("scroll", edges, { passive: true });
  new ResizeObserver(edges).observe(strip);
  // Bring the selected tab into the strip's view without scrolling the page (scrollIntoView would).
  const reveal = (tab) => {
    const a = strip.getBoundingClientRect(), b = tab.getBoundingClientRect();
    if (b.left < a.left) strip.scrollLeft -= a.left - b.left + 40;
    else if (b.right > a.right) strip.scrollLeft += b.right - a.right + 40;
  };

  // The selected award lives in the URL (#opoy) so a link opens on that tab; MVP keeps the plain URL.
  const fromHash = () => Math.max(0, awards.indexOf(location.hash.slice(1)));
  function select(i) {
    tabs.forEach((tab, j) => {
      tab.setAttribute("aria-selected", String(i === j));
      tab.tabIndex = i === j ? 0 : -1;
    });
    $("panel").setAttribute("aria-labelledby", tabs[i].id);
    reveal(tabs[i]);
    history.replaceState(null, "", i === 0 ? location.pathname + location.search : `#${awards[i]}`);
    render(awards[i], latest, teams, weeks);
  }
  addEventListener("hashchange", () => select(fromHash()));
  // One opening moment: the share bars and the vote bar draw in once. Sorting or switching tabs won't replay it.
  document.documentElement.classList.add("intro");
  setTimeout(() => document.documentElement.classList.remove("intro"), 1200);

  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => select(i));
    tab.addEventListener("keydown", (e) => {
      const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
      if (!step) return;
      const next = (i + step + tabs.length) % tabs.length;
      tabs[next].focus();
      select(next);
    });
  });
  select(fromHash());
}

function render(award, latest, teams, weeks) {
  const { short, full } = awardName(award);
  const rows = latest.awards[award] || [];
  const week = latest.through_week;
  $("title").textContent = `${short} race`;
  document.title = `Award Watch: NFL ${short} race`;
  const lede = `The model's predicted share of the AP ${full} vote, from this season's stats.`;
  if ($("lede").textContent !== lede) $("lede").textContent = lede; // the MVP line is already in the HTML
  const how = HOW_IT_WORKS[award] || `${RETRAINED} every candidate in the pool. ${shares("candidates", "candidate")}`;
  if ($("how-text").textContent.replace(/\s+/g, " ").trim() !== how) $("how-text").textContent = how;
  $("panel").setAttribute("aria-busy", "false");
  if (!rows.length) {
    showMessage(`No ${full} predictions in this week's file yet.`);
    return;
  }
  $("content").hidden = false;
  $("ticker-bar").hidden = false;
  const team = (r) => teams[r.team] || {};
  const set = statSet(award);

  renderTicker(rows, week);
  renderHero(rows, week, team, set);
  renderBoard(rows, team, set);
  renderTrend(award, rows.slice(0, SERIES.length), weeks);
  renderSwings(award, rows, weeks, week);
  renderHeadToHead(rows, set);
}

// ---------- Ticker ----------

function renderTicker(rows, week) {
  $("ticker").setAttribute("aria-label", `Top 10 through week ${week}`);
  $("ticker").replaceChildren(
    el("li", { class: "tick-label", "aria-hidden": "true" }, el("strong", { text: "Top 10" })),
    ...rows.map((r) => el("li", {},
      el("p", { class: "tick-name", title: r.player }, el("small", { text: String(r.rank) }), lastName(r.player)),
      el("p", { class: "tick-line" }, el("span", { class: "tick-share", text: pct(r.share) }),
        move(shareChange(r) == null ? null : shareChange(r) * 100, { words: " points since last week" })))));
}

// ---------- Leader card ----------

function renderHero(rows, week, team, set) {
  const lead = rows[0];
  const second = rows[1];
  const t = team(lead);
  const vars = t.color ? { "--team": t.color } : {};
  const change = shareChange(lead);
  const margin = second ? lead.share - second.share : null;

  const stat = (cls, label, value, unit) => el("div", { class: cls },
    el("dt", { text: label }), el("dd", {}, value, unit ? el("small", { text: unit }) : null));

  const top5 = rows.slice(0, NIGHT.length);
  const rest = Math.max(0, 1 - top5.reduce((sum, r) => sum + r.share, 0));
  const parts = [...top5.map((r, i) => ({ label: lastName(r.player), share: r.share, color: `var(${NIGHT[i]})` })),
    { label: "Everyone else", share: rest, color: "var(--n-other)" }];

  $("hero").replaceChildren(
    el("div", { class: "hero-top", vars },
      avatar(lead, "hero-avatar", 208),
      el("div", { class: "hero-id" },
        el("h2", { class: "hero-name", id: "hero-name", text: lead.player }),
        el("p", { class: "hero-meta" }, el("span", { class: "team-chip", "aria-hidden": "true" }),
          `${lead.position} · ${t.name || lead.team} · ${lead.team_record}`)),
      el("p", { class: "hero-share" },
        el("span", { class: "big", text: pct(lead.share) }),
        el("span", { class: "cap", text: "of the projected vote" }),
        el("span", { class: "hero-share-sub" },
          change == null ? null : el("span", {}, move(change * 100), ` pts since week ${week - 1}`),
          margin == null ? null : el("span", { text: `${pts(margin)} pts ahead of ${lastName(second.player)}` })))),
    el("dl", { class: "hero-stats" },
      change == null
        ? stat("stat-context", "Last week", el("span", { class: "flat", text: "New" }))
        : stat("stat-context", `Since week ${week - 1}`, move(change * 100), "pts"),
      margin == null ? stat("stat-context", "Lead", "–")
        // a long surname ("Smith-Njigba") would truncate in the label cell
        : stat("stat-context", lastName(second.player).length <= 9 ? `Lead over ${lastName(second.player)}` : "Lead over No. 2", pts(margin), "pts"),
      ...set.map((st) => stat("stat-core", st.label, showStat(st, lead)))),
    el("div", { class: "vote" },
      el("p", { class: "vote-label", id: "vote-label", text: "The vote if the season ended today" }),
      el("div", { class: "vote-bar", role: "img", "aria-labelledby": "vote-label vote-legend" },
        ...parts.map((p) => el("span", { vars: { "--seg": p.color, width: `${p.share * 100}%` } }))),
      el("ul", { class: "vote-legend", id: "vote-legend" }, ...parts.map((p) => el("li", {},
        el("span", { class: "swatch", "aria-hidden": "true", vars: { "--seg": p.color } }),
        el("b", { text: p.label }), el("span", { class: "num", text: pct(p.share) }))))));
}

// ---------- Top 10 table ----------

const columnsFor = (set) => [
  // key, label, first sort direction (1 = ascending), cell class, value for sorting
  ["rk", "Rk", 1, "c-rk", (r) => r.rank],
  ["player", "Player", 1, "c-player", (r) => lastName(r.player)],
  ["rec", "Rec", -1, "c-stat c-rec", (r) => winPct(r.team_record)],
  // where fewer is better (turnovers), the first click sorts low to high
  ...set.map((st) => [st.key, st.label, st.lower ? 1 : -1, "c-stat", (r) => r.stats[st.key]]),
  ["share", "Share", -1, "c-share", (r) => r.share],
  ["chg", "Chg", -1, "c-chg", (r) => shareChange(r) ?? -Infinity],
];

function renderBoard(rows, team, set) {
  const COLUMNS = columnsFor(set);
  const sort = { key: "rk", dir: 1 };
  const heads = COLUMNS.map(([key, label, firstDir, cls]) => {
    const button = el("button", { class: "sort", type: "button" }, label);
    const th = el("th", { scope: "col", class: cls }, button);
    button.addEventListener("click", () => {
      sort.dir = sort.key === key ? -sort.dir : firstDir;
      sort.key = key;
      paint();
    });
    return th;
  });
  $("board-head").replaceChildren(...heads);

  const rowFor = (r) => {
    const t = team(r);
    const vars = t.color ? { "--team": t.color } : {};
    const stats = set.map((st) => `${showStat(st, r)} ${st.unit}`);
    return el("tr", {},
      el("td", { class: "c-rk" }, el("div", { class: "rk" }, el("strong", { text: String(r.rank) }),
        move(rankChange(r), { digits: 0, words: " spots since last week" }))),
      el("td", { class: "c-player" }, el("div", { class: "player", vars },
        avatar(r, "avatar", 80),
        el("div", { class: "who" },
          el("p", { class: "who-name", text: r.player }),
          el("p", { class: "who-meta" }, el("span", { class: "team-chip", "aria-hidden": "true" }),
            `${r.position} · ${r.team}`, el("span", { class: "rec-inline", text: `· ${r.team_record}` })),
          el("p", { class: "who-stats" }, ...stats.map((x) => el("span", { text: x })))))), // separators come from CSS
      el("td", { class: "c-stat c-rec", text: r.team_record }),
      ...set.map((st) => el("td", { class: "c-stat", text: showStat(st, r) })),
      el("td", { class: "c-share" }, el("div", { class: "share" },
        el("span", { class: "share-bar", "aria-hidden": "true" }, el("span", { vars: { width: `${r.share * 100}%` } })),
        el("span", { class: "share-pct", text: pct(r.share) }))),
      el("td", { class: "c-chg" }, move(shareChange(r) == null ? null : shareChange(r) * 100, { words: " points since last week" })));
  };

  function paint() {
    heads.forEach((th, i) => {
      const on = COLUMNS[i][0] === sort.key;
      th.setAttribute("aria-sort", on ? (sort.dir > 0 ? "ascending" : "descending") : "none");
      const button = th.querySelector(".sort");
      button.querySelector("svg")?.remove();
      if (on) button.append(icon(sort.dir > 0 ? "asc" : "desc"));
    });
    const value = COLUMNS.find((c) => c[0] === sort.key)[4];
    const sorted = [...rows].sort((a, b) => {
      const x = value(a), y = value(b);
      return x < y ? -sort.dir : x > y ? sort.dir : a.rank - b.rank;
    });
    $("board-body").replaceChildren(...sorted.map(rowFor));
  }
  paint();

  const rest = Math.max(0, 1 - rows.reduce((sum, r) => sum + r.share, 0));
  $("board-foot").replaceChildren(
    el("td", { colspan: String(3 + set.length), class: "c-player", text: "Everyone else in the pool" }),
    el("td", { class: "c-share" }, el("div", { class: "share" }, el("span", { class: "share-pct", text: pct(rest) }))),
    el("td", { class: "c-chg" }));
}

// ---------- Share-by-week chart ----------

let redraw = null;
new ResizeObserver(() => redraw && requestAnimationFrame(redraw)).observe($("chart"));

function renderTrend(award, top, weeks) {
  const chart = $("chart");
  if (!weeks.length) {
    chart.replaceChildren(el("p", { class: "chart-note", text: "The week-by-week files didn't load, so there's no trend to show." }));
    $("readout").replaceChildren();
    $("chart-table").replaceChildren();
    redraw = null;
    return;
  }
  const xWeeks = weeks.map((w) => w.through_week);
  const series = top.map((p, i) => ({
    name: p.player,
    label: lastName(p.player),
    color: `var(${SERIES[i]})`,
    values: weeks.map((w) => {
      const hit = (w.awards[award] || []).find((r) => r.player_id === p.player_id);
      return hit ? hit.share : null; // null = outside that week's top 10
    }),
  }));

  // The legend doubles as the readout: it always shows every series at one week.
  const chip = el("span", { class: "week-chip" });
  const values = series.map(() => el("span", { class: "num" }));
  $("readout").replaceChildren(chip, el("ul", { class: "readout", "aria-hidden": "true" }, ...series.map((s, i) => el("li", {},
    el("span", { class: "key", vars: { "--series": s.color } }), el("b", { text: s.label }), values[i]))));
  const setReadout = (i) => {
    chip.textContent = `Week ${xWeeks[i]}`;
    series.forEach((s, k) => { values[k].textContent = s.values[i] == null ? "–" : pct(s.values[i]); });
  };
  setReadout(xWeeks.length - 1);
  renderTable(series, xWeeks);

  redraw = () => drawChart(chart, series, xWeeks, setReadout);
  redraw();
}

function niceScale(max) {
  const step = [0.05, 0.1, 0.25].find((s) => max / s <= 5) || 0.25;
  return { step, top: Math.max(step, Math.ceil(max / step) * step) };
}

function drawChart(box, series, xWeeks, setReadout) {
  const W = Math.max(box.clientWidth, 280);
  const narrow = W < 520;
  const H = Math.round(Math.min(300, Math.max(210, W * 0.42)));
  const m = { top: 10, right: narrow ? 64 : 104, bottom: 28, left: 40 };
  const iw = W - m.left - m.right;
  const ih = H - m.top - m.bottom;
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  const { step, top } = niceScale(Math.max(...all, 0.05));
  const n = xWeeks.length;
  const xAt = (i) => m.left + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
  const yAt = (v) => m.top + ih - (v / top) * ih;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });
  const grid = svgEl("g", { class: "grid" });
  for (let v = step; v <= top + 1e-9; v += step) grid.append(svgEl("line", { x1: m.left, x2: m.left + iw, y1: yAt(v), y2: yAt(v) }));
  svg.append(grid, svgEl("line", { class: "baseline", x1: m.left, x2: m.left + iw, y1: yAt(0), y2: yAt(0) }));
  for (let v = 0; v <= top + 1e-9; v += step) {
    const t = svgEl("text", { class: "tick", x: m.left - 8, y: yAt(v) + 4, "text-anchor": "end" });
    t.textContent = `${Math.round(v * 100)}%`;
    svg.append(t);
  }
  const every = iw / Math.max(n - 1, 1) < 26 ? 2 : 1; // thin the week labels when they'd crowd
  xWeeks.forEach((w, i) => {
    // Count back from the current week, always keep "Wk 1" so the axis names its unit,
    // and drop any label that would sit right beside it.
    if (i !== 0 && ((n - 1 - i) % every || i < every)) return;
    const t = svgEl("text", { class: "tick", x: xAt(i), y: H - 8, "text-anchor": "middle" });
    t.textContent = i === 0 ? `Wk ${w}` : String(w);
    svg.append(t);
  });

  // Lines, broken where a player was outside the top 10, with a ringed dot at each line's end.
  const labels = [];
  for (const s of series) {
    const g = svgEl("g", { class: "series" });
    let d = "";
    let prev = null;
    s.values.forEach((v, i) => {
      if (v == null) { prev = null; return; }
      d += `${prev == null ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`;
      if (prev == null && s.values[i + 1] == null && i !== n - 1) g.append(svgEl("circle", { cx: xAt(i), cy: yAt(v), r: 3 }, { fill: s.color }));
      prev = v;
    });
    g.append(svgEl("path", { d }, { stroke: s.color }));
    const last = s.values.at(-1);
    if (last != null) {
      g.append(svgEl("circle", { cx: xAt(n - 1), cy: yAt(last), r: 4 }, { fill: s.color }));
      labels.push({ y: yAt(last), name: s.label, value: pct(last) });
    }
    svg.append(g);
  }

  // Direct end labels, only where they don't collide; the readout above covers the rest.
  labels.sort((a, b) => a.y - b.y);
  let lastY = -Infinity;
  for (const l of labels) {
    if (l.y - lastY < 15) continue;
    const t = svgEl("text", { class: "end-label", x: xAt(n - 1) + 9, y: l.y + 4 });
    const nm = svgEl("tspan");
    nm.textContent = l.name;
    t.append(nm, document.createTextNode(narrow ? "" : ` ${l.value}`));
    svg.append(t);
    lastY = l.y;
  }

  // Hover and keyboard layer: a crosshair snaps to the nearest week and the readout follows it.
  const cross = svgEl("line", { class: "crosshair", y1: m.top, y2: m.top + ih, visibility: "hidden" });
  const hoverDots = svgEl("g", { class: "series" });
  const hit = svgEl("rect", { x: m.left - 12, y: 0, width: iw + 24, height: H, fill: "transparent" });
  svg.append(cross, hoverDots, hit);

  const live = el("p", { class: "visually-hidden", "aria-live": "polite" });
  box.replaceChildren(svg, live);
  box.tabIndex = 0;
  box.setAttribute("aria-label",
    "Line chart of predicted share by week for this week's top five. Use the left and right arrow keys to read each week; the table view below has every value.");

  let current = null;
  function show(i, announce) {
    current = i;
    const x = xAt(i);
    cross.setAttribute("x1", x);
    cross.setAttribute("x2", x);
    cross.setAttribute("visibility", "visible");
    hoverDots.replaceChildren(...series.filter((s) => s.values[i] != null)
      .map((s) => svgEl("circle", { cx: x, cy: yAt(s.values[i]), r: 4 }, { fill: s.color })));
    setReadout(i);
    if (announce) {
      live.textContent = `Week ${xWeeks[i]}: ` + series.map((s) =>
        `${s.name} ${s.values[i] == null ? "outside the top 10" : pct(s.values[i])}`).join(", ");
    }
  }
  function hide() {
    current = null;
    cross.setAttribute("visibility", "hidden");
    hoverDots.replaceChildren();
    setReadout(n - 1);
  }
  hit.addEventListener("pointermove", (e) => {
    const rect = svg.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * W;
    const i = n === 1 ? 0 : Math.round(((sx - m.left) / iw) * (n - 1));
    show(Math.min(n - 1, Math.max(0, i)), false);
  });
  hit.addEventListener("pointerleave", hide);
  box.onfocus = () => show(current ?? n - 1, true);
  box.onblur = hide;
  box.onkeydown = (e) => {
    const steps = { ArrowLeft: -1, ArrowRight: 1, Home: -n, End: n };
    if (e.key === "Escape") return hide();
    if (!(e.key in steps)) return;
    e.preventDefault();
    show(Math.min(n - 1, Math.max(0, (current ?? n - 1) + steps[e.key])), true);
  };
}

function renderTable(series, xWeeks) {
  const table = el("table", {},
    el("caption", { class: "visually-hidden", text: "Predicted share by week, this week's top five" }),
    el("thead", {}, el("tr", {}, el("th", { scope: "col", text: "Week" }),
      ...series.map((s) => el("th", { scope: "col", text: s.label })))),
    el("tbody", {}, ...xWeeks.map((w, i) => el("tr", {}, el("th", { scope: "row", text: String(w) }),
      ...series.map((s) => el("td", { text: s.values[i] == null ? "–" : pct(s.values[i]) }))))));
  $("chart-table").replaceChildren(table);
}

// ---------- This week's swings ----------
// Short, factual notes about who moved, written from the numbers. No pronouns: the rows are real people.

function streak(award, row, weeks) {
  const s = weeks.map((w) => (w.awards[award] || []).find((r) => r.player_id === row.player_id)?.share ?? null);
  let count = 0;
  for (let i = s.length - 1; i > 0 && s[i] != null && s[i - 1] != null && s[i] > s[i - 1]; i--) count++;
  return count;
}

function swingItems(award, rows, weeks) {
  const items = [];
  const used = new Set();
  const L = (r) => lastName(r.player);
  const withShare = rows.filter((r) => r.prev_share != null);
  const byChange = [...withShare].sort((a, b) => shareChange(b) - shareChange(a));

  const gain = byChange[0];
  if (gain && shareChange(gain) >= 0.005) {
    const n = streak(award, gain, weeks);
    items.push({ delta: shareChange(gain) * 100, unit: "points",
      title: `${L(gain)} adds ${pts(shareChange(gain))} points`,
      detail: `${pct(gain.prev_share)} to ${pct(gain.share)}${n >= 2 ? `, a ${ordinal(n)} straight weekly gain` : ""}.` });
    used.add(gain.player_id);
  }
  const loss = byChange.at(-1);
  if (loss && shareChange(loss) <= -0.005 && !used.has(loss.player_id)) {
    const [now, before] = ordinalPair(loss.rank, loss.prev_rank);
    const where = loss.rank === loss.prev_rank ? `Still ${now}.` : `Now ${now}, from ${before}.`;
    items.push({ delta: shareChange(loss) * 100, unit: "points",
      title: `${L(loss)} gives back ${pts(shareChange(loss))} points`,
      detail: `${pct(loss.prev_share)} to ${pct(loss.share)}. ${where}` });
    used.add(loss.player_id);
  }

  const movers = rows.filter((r) => r.prev_rank != null && !used.has(r.player_id));
  const climbGroups = Object.entries(Object.groupBy(movers.filter((r) => rankChange(r) >= 2), rankChange))
    .map(([d, group]) => ({ d: Number(d), group })).sort((a, b) => b.d - a.d);
  const climb = ({ d, group }) => {
    group.forEach((r) => used.add(r.player_id));
    if (group.length === 1) {
      const r = group[0];
      const [from, to] = ordinalPair(r.prev_rank, r.rank);
      // a climb can come from others falling, with the share the same to one decimal
      const how = pct(r.prev_share) === pct(r.share) ? `with the share steady at ${pct(r.share)}`
        : `on a move from ${pct(r.prev_share)} to ${pct(r.share)}`;
      return { delta: d, unit: "spots", title: `${L(r)} ${d >= 5 ? "jumps" : "climbs"} ${numberWord(d)} spots`,
        detail: `${cap(from)} to ${to}, ${how}.` };
    }
    const names = group.map(L);
    const sameStart = group.every((r) => pct(r.prev_share) === pct(group[0].prev_share));
    return { delta: d, unit: "spots each",
      title: `${names.slice(0, -1).join(", ")} and ${names.at(-1)} climb ${numberWord(d)} spots each`,
      detail: sameStart ? `${group.length === 2 ? "Both" : "All"} sat at ${pct(group[0].prev_share)} a week ago.`
        : group.map((r) => `${L(r)} ${ordinalPair(r.prev_rank, r.rank).join(" to ")}`).join(", ") + "." };
  };
  if (climbGroups[0]) items.push(climb(climbGroups[0]));

  const drop = movers.filter((r) => !used.has(r.player_id) && rankChange(r) <= -2).sort((a, b) => rankChange(a) - rankChange(b))[0];
  if (drop) {
    items.push({ delta: rankChange(drop), unit: "spots", title: `${L(drop)} slides to ${ordinal(drop.rank)}`,
      detail: `${cap(ordinal(drop.prev_rank))} last week at ${pct(drop.prev_share)}, now at ${pct(drop.share)}.` });
    used.add(drop.player_id);
  }
  if (climbGroups[1]) items.push(climb(climbGroups[1]));

  for (const r of rows.filter((r) => r.prev_rank == null)) {
    items.push({ delta: null, unit: "new", title: `${L(r)} enters the race`,
      detail: `Outside the candidate pool last week, now ${ordinal(r.rank)} at ${pct(r.share)}.` });
  }
  return items.slice(0, 5);
}

function renderSwings(award, rows, weeks, week) {
  $("swings-meta").textContent = week > 1 ? `Week ${week - 1} to week ${week}` : "";
  const items = week > 1 ? swingItems(award, rows, weeks) : [];
  if (!items.length) {
    $("swings").replaceChildren(el("li", {}, el("span", { class: "empty", text:
      week > 1 ? "A quiet week: nobody in the top 10 moved more than half a point or two spots." : "Movement shows up after week 2." })));
    return;
  }
  $("swings").replaceChildren(...items.map((it) => {
    const kind = it.delta == null ? "flat" : it.delta > 0 ? "up" : "down";
    const amount = it.delta == null ? "New" : it.unit === "points" ? Math.abs(it.delta).toFixed(1) : String(Math.abs(it.delta));
    return el("li", {},
      el("div", {},
        el("p", { class: `swing-val ${kind}` }, it.delta == null ? null : icon(kind), amount),
        it.delta == null ? null : el("span", { class: "swing-unit", text: it.unit })),
      el("div", {}, el("p", { class: "swing-title", text: it.title }), el("p", { class: "swing-detail", text: it.detail })));
  }));
}

// ---------- Head to head ----------

function renderHeadToHead(rows, set) {
  const [a, b] = rows;
  if (!b) {
    $("h2h-card").hidden = true;
    return;
  }
  $("h2h-card").hidden = false;
  const lower = set.filter((st) => st.lower);
  const metrics = [
    // label, value, display, then true if lower is better, false if higher, null if neither (no bold).
    // Fewer-is-better stats go last, next to the note.
    ["Share", (r) => r.share, (r) => pct(r.share), false],
    ...[...set.filter((st) => !st.lower), ...lower].map((st) => [st.long || st.label, (r) => r.stats[st.key], (r) => showStat(st, r),
      st.neutral ? null : Boolean(st.lower)]),
    ["Record", (r) => winPct(r.team_record), (r) => r.team_record, false],
  ];
  const colors = ["var(--s1)", "var(--s2)"];
  $("h2h").replaceChildren(
    el("div", { class: "h2h-names" },
      el("span", {}, el("span", { class: "key", "aria-hidden": "true", vars: { "--series": colors[0] } }), lastName(a.player)),
      el("span", {}, lastName(b.player), el("span", { class: "key", "aria-hidden": "true", vars: { "--series": colors[1] } }))),
    ...metrics.map(([label, value, show, lowerBetter]) => {
      const va = value(a), vb = value(b);
      const top = Math.max(va, vb, 0) || 1;
      const better = va === vb || lowerBetter == null ? null : (va > vb) !== lowerBetter ? "a" : "b";
      const half = (side, v, color) => el("div", { class: `h2h-half ${side}`, "aria-hidden": "true" },
        el("span", { vars: { width: `${Math.max(v, 0) / top * 100}%`, "--series": color } }));
      return el("div", { class: "h2h-row", role: "group", "aria-label": `${label}: ${a.player} ${show(a)}, ${b.player} ${show(b)}` },
        el("p", { class: "h2h-label", text: label }),
        el("span", { class: `h2h-val a${better === "a" ? " better" : ""}`, text: show(a) }),
        half("a", va, colors[0]), half("b", vb, colors[1]),
        el("span", { class: `h2h-val b${better === "b" ? " better" : ""}`, text: show(b) }));
    }),
    el("p", { class: "h2h-note", text: ["Bold marks the better number.",
      ...lower.map((st) => `Fewer ${(st.long || st.label).toLowerCase()} is better.`)].join(" ") }));
}

main();
