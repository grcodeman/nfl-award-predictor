// Game picks and the scoreboard: the Games and Scoreboard tabs, from the pick ledger in ../predictions/games/.
// Uses the helpers in app.js (el, svgEl, $, getJSON, icon). Loaded after it.
"use strict";

const LEDGER = "games/";
const MODEL_NAMES = { "games-elo": "Elo" }; // what the page calls each game model
const modelName = (m) => MODEL_NAMES[m] || m;
const SCORERS = { market: "Market at lock", closing: "Closing line", home: "Always home" };
const scorerName = (s) => SCORERS[s.scorer] || modelName(s.scorer);
const ledgerCache = {};
const ledgerJSON = (path) => (ledgerCache[path] ??= getJSON(LEDGER + path));
const weekFile = (kind, season, week) => `${kind}/${season}/week_${String(week).padStart(2, "0")}.json`;

const prob = (p) => `${Math.round(p * 100)}%`;
const minus = (x) => (x < 0 ? `−${Math.abs(x)}` : String(x));
const half = (x) => (x % 1 ? `${Math.floor(x) || ""}½` : String(x)); // a 50% call counts half a win
const record = (s) => `${half(s.correct)}–${half(s.games - s.correct)}`;
const rate = (s) => (s.games ? `${(100 * s.correct / s.games).toFixed(1)}%` : "–");
const fixed = (x, d) => (x == null ? "–" : x.toFixed(d));
const nick = (teams, code) => (teams[code]?.name || code).split(" ").at(-1);
const marketProb = (spread) => 0.5 * (1 + erf(spread / (13.5 * Math.SQRT2)));
function erf(x) { // Abramowitz-Stegun 7.1.26, good to 1e-7: plenty for a percentage
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return Math.sign(x) * y;
}
// "KC −3.5": the favorite and the points it gives. spread is points the home team is favored by.
const spreadText = (g) => (g.market_spread == null ? "No line at lock" : g.market_spread === 0 ? "Pick'em"
  : g.market_spread > 0 ? `${g.home} ${minus(-g.market_spread)}` : `${g.away} ${minus(g.market_spread)}`);
const when = (iso, opts) => new Date(iso).toLocaleString(undefined, opts);
const kickoffTime = (iso) => when(iso, { hour: "numeric", minute: "2-digit" });
const lockTime = (iso) => when(iso, { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

function setStatus(...parts) {
  $("status").replaceChildren(...parts.flatMap((p, i) => [
    ...(i ? [el("span", { class: "sep", "aria-hidden": "true", text: " · " })] : []), el("span", { text: p })]));
}

// Which view shows: the award layout, or one of these two.
function showView(id) {
  for (const v of ["content", "games-content", "score-content"]) $(v).hidden = v !== id;
  $("ticker-bar").hidden = id !== "content";
  $("message").hidden = true;
}

function setTitle(title, lede, tab) {
  $("title").textContent = title;
  $("lede").textContent = lede;
  document.title = `Award Watch: NFL ${tab}`;
  $("panel").setAttribute("aria-busy", "false");
}

function emptyCard(heading, text) {
  return el("section", { class: "card" }, el("div", { class: "card-head" }, el("h2", { text: heading })),
    el("p", { class: "card-body empty-note", text }));
}

function card(heading, meta, ...body) {
  return el("section", { class: "card" },
    el("div", { class: "card-head" }, el("h2", { text: heading }), meta ? el("p", { class: "card-meta", text: meta }) : null),
    ...body);
}

const HOW_PICKS = [
  "Every team has an Elo rating, built from every game since 1999. A win moves a rating up and a loss down, more for a bigger margin and less for a favorite, and each offseason pulls every team a little back toward average. The home team gets 55 rating points, about two points on the scoreboard.",
  "A week's picks are written and committed before its first kickoff and never changed, so the record can't be edited after the fact. The market line is the point spread at that moment; a spread becomes a win probability through a bell curve with a 13.5-point standard deviation.",
  "Elo knows only scores: no injuries, no quarterback news. The market knows everything, so Elo should trail it. The point is to measure by how much, and where.",
];

function rail(id, heading, paragraphs, credits = true) {
  $(id).replaceChildren(card(heading, null, el("div", { class: "card-body prose" },
    ...paragraphs.map((p) => el("p", { text: p })),
    credits ? el("p", { class: "credits" }, "Schedules, scores and lines from ", el("a", { href: "https://nflverse.nflverse.com/", text: "nflverse" }),
      ". Not affiliated with the NFL.") : null)));
}

// ---------- Games tab ----------

async function renderGames(teams) {
  showView("games-content");
  rail("games-rail", "How the picks work", HOW_PICKS);
  let index;
  try {
    index = await ledgerJSON("index.json");
  } catch (err) {
    console.error(err);
    index = { latest_picks: null };
  }
  const latest = index.latest_picks;
  if (!latest) {
    setTitle("Game picks", "Elo's pick for every game, locked before kickoff, next to the betting market.", "game picks");
    setStatus("Game picks");
    $("games-main").replaceChildren(emptyCard("No picks yet",
      "The first live picks are for week 13. They're written the Tuesday before its first kickoff and show up here, with the market line beside each one."));
    return;
  }
  const picks = await ledgerJSON(weekFile("picks", latest.season, latest.week));
  const results = (index.results[String(latest.season)] || []).includes(latest.week)
    ? await ledgerJSON(weekFile("results", latest.season, latest.week)).catch(() => null) : null;
  setTitle(`${picks.label} picks`, "Elo's pick for every game, locked before kickoff, next to the betting market.", `${picks.label} picks`);
  setStatus(`${picks.season} season · ${picks.label} picks`, `Locked ${when(picks.written_at, { month: "short", day: "numeric" })}`);
  $("games-main").replaceChildren(...gamesBody(picks, results, teams));
}

// One game's numbers: Elo's favorite and its probability, the market's for the same team, and the result.
function gameView(g, pick, final) {
  const homeFav = pick.home_win_prob >= 0.5;
  const fav = homeFav ? g.home : g.away;
  const p = homeFav ? pick.home_win_prob : 1 - pick.home_win_prob;
  const mHome = g.market_spread == null ? null : marketProb(g.market_spread);
  const m = mHome == null ? null : homeFav ? mHome : 1 - mHome; // the market's number for Elo's favorite
  const split = m != null && m < 0.5;
  const out = { g, pick, fav, p, m, split, margin: Math.abs(pick.home_margin) };
  if (final) {
    const diff = final.home_score - final.away_score;
    out.final = final;
    out.winner = diff > 0 ? g.home : diff < 0 ? g.away : null;
    out.eloRight = out.winner == null ? null : out.winner === fav;
    out.marketRight = out.winner == null || mHome == null || mHome === 0.5 ? null : (mHome > 0.5) === (diff > 0);
  }
  return out;
}

function gamesBody(picks, results, teams) {
  const finals = Object.fromEntries((results?.games || []).map((r) => [r.game_id, r]));
  const champ = picks.picks.filter((p) => p.model === picks.champion.model && p.version === picks.champion.version);
  const byGame = Object.fromEntries(champ.map((p) => [p.game_id, p]));
  const views = picks.games.map((g) => gameView(g, byGame[g.game_id], finals[g.game_id]));
  const lined = views.filter((v) => v.m != null);
  const agree = lined.filter((v) => !v.split).length;
  const graded = views.filter((v) => v.eloRight != null);
  const stat = (label, value, sub) => el("div", {}, el("dt", { text: label }), el("dd", {}, value), sub ? el("p", { class: "sub", text: sub }) : null);
  const scores = results?.scores || [];
  const elo = scores.find((s) => s.scorer === picks.champion.model && s.version === picks.champion.version);
  const market = scores.find((s) => s.scorer === "market");

  const summary = el("section", { class: "card" }, el("dl", { class: "stat-strip" },
    stat("Locked", lockTime(picks.written_at), `First kickoff ${lockTime(picks.first_kickoff)}`),
    stat("Elo and the market", lined.length ? `Agree on ${agree} of ${lined.length}` : "No lines yet",
      lined.length < views.length ? `${views.length - lined.length} game${views.length - lined.length > 1 ? "s" : ""} had no line at lock` : "on who wins"),
    graded.length && elo
      ? stat("This week", `Elo ${record(elo)}`, market?.games ? `Market ${record(market)}` : null)
      : stat("Games", String(views.length), `${modelName(picks.champion.model)} v${picks.champion.version}`)));

  // Group by day, in kickoff order.
  const days = Object.groupBy(views, (v) => when(v.g.kickoff, { weekday: "long", month: "short", day: "numeric" }));
  const list = el("div", { class: "games" }, ...Object.entries(days).map(([day, vs]) => el("div", { class: "game-day" },
    el("h3", { class: "day-head", text: day }),
    el("ul", { class: "game-list" }, ...vs.map((v) => gameRow(v, teams))))));
  const legend = el("p", { class: "card-meta pick-legend" },
    el("span", { class: "key-bar", "aria-hidden": "true" }), "Elo", el("span", { class: "key-tick", "aria-hidden": "true" }), "Market");
  const gamesCard = el("section", { class: "card" },
    el("div", { class: "card-head" }, el("h2", { text: "Games" }), legend), list);
  return [summary, gamesCard];
}

function teamLine(teams, code, score, won) {
  const t = teams[code] || {};
  return el("p", { class: `team-line${won ? " won" : ""}` },
    t.logo ? teamLogo(t.logo, "team-logo", false, (pic) => pic.remove()) : null,
    el("span", { class: "team-code", text: code }), el("span", { class: "team-nick", text: nick(teams, code) }),
    score == null ? null : el("span", { class: "team-score", text: String(score) }));
}

function verdict(label, right) {
  if (right == null) return null;
  return el("span", { class: `verdict ${right ? "up" : "down"}` },
    el("span", { "aria-hidden": "true", text: right ? "✓" : "✗" }), `${label} ${right ? "right" : "wrong"}`);
}

function gameRow(v, teams) {
  const { g, fav, p, m, split, final } = v;
  const bar = el("div", { class: "pick-bar", "aria-hidden": "true" },
    el("span", { class: "fill", vars: { width: `${p * 100}%` } }),
    m == null ? null : el("span", { class: "tick", vars: { left: `${m * 100}%` } }));
  const label = `${g.away} at ${g.home}: Elo picks ${fav}, ${prob(p)}, by ${v.margin.toFixed(1)}. Market: ${spreadText(g)}`
    + (m == null ? "." : `, ${prob(m)} for ${fav}.`)
    + (final ? ` Final: ${g.away} ${final.away_score}, ${g.home} ${final.home_score}.` : "");
  return el("li", { class: `game${final ? " is-final" : ""}`, "aria-label": label },
    el("div", { class: "game-when" },
      el("span", { class: "kick", text: final ? "Final" : kickoffTime(g.kickoff) }),
      split ? el("span", { class: "split", text: "Split" }) : null),
    el("div", { class: "game-teams" },
      teamLine(teams, g.away, final?.away_score, final && v.winner === g.away),
      teamLine(teams, g.home, final?.home_score, final && v.winner === g.home),
      g.neutral ? el("p", { class: "game-note", text: "Neutral site" }) : null),
    el("div", { class: "game-pick" },
      el("p", { class: "pick-head" }, el("span", { class: "pick-team", text: fav }), el("span", { class: "pick-prob", text: prob(p) }),
        el("span", { class: "pick-margin", text: `by ${v.margin.toFixed(1)}` })),
      bar,
      el("p", { class: "pick-market", text: m == null ? spreadText(g) : `Market ${spreadText(g)} · ${prob(m)} ${fav}` })),
    final ? el("div", { class: "game-result" }, verdict("Elo", v.eloRight), verdict("Market", v.marketRight),
      v.winner == null ? el("span", { class: "verdict flat", text: "Tie" }) : null) : null);
}

// ---------- Scoreboard tab ----------

async function renderScoreboard() {
  showView("score-content");
  setTitle("Scoreboard", "How Elo's live picks are doing against the betting market, and how it did over eleven past seasons.", "scoreboard");
  rail("score-rail", "Reading the scores", [
    "Winners picked counts a game for whoever the model favored. Log loss and the Brier score grade the probability itself: a confident miss costs much more than a coin-flip miss. Lower is better for both.",
    "The market at lock is the spread when the picks were written, with the same news Elo had. The closing line is the last spread before kickoff: the best public forecast there is.",
    "A week is too few games to tell much. Lean on the season totals and on the backtest, which replays 3,000 games.",
  ]);
  setStatus("Scoreboard");
  const main = $("score-main");
  main.replaceChildren(el("p", { class: "empty-note", text: "Loading…" }));
  let sb, index, bt;
  try {
    [sb, index] = await Promise.all([ledgerJSON("scoreboard.json"), ledgerJSON("index.json")]);
    bt = await ledgerJSON(sb.backtest.replace(/^games\//, ""));
  } catch (err) {
    console.error(err);
    main.replaceChildren(emptyCard("Scoreboard", "Couldn't load the scores. Check your connection, then refresh the page."));
    return;
  }
  const seasons = Object.keys(sb.seasons).sort();
  const season = seasons.at(-1);
  const live = season ? await liveSection(sb, season, index) : [emptyCard("Live picks",
    "The first live picks are for week 13, locked before its first kickoff. Their grades land here the Tuesday after, next to the market's.")];
  if (season) setStatus(`${season} season`, `Graded through ${sb.seasons[season].weeks.at(-1).label.toLowerCase()}`);
  main.replaceChildren(...live, ...backtestSection(bt));
}

function scoreTable(rows, caption) {
  return el("div", { class: "table-scroll" }, el("table", { class: "scores" },
    el("caption", { class: "visually-hidden", text: caption }),
    // c-extra columns step aside on phones
    el("thead", {}, el("tr", {}, ...[["", "c-name"], ["Picked"], ["Hit rate"], ["Log loss"], ["Brier", "c-extra"], ["Avg miss", "c-extra"]]
      .map(([h, cls]) => el("th", { scope: "col", class: cls, text: h })))),
    el("tbody", {}, ...rows.map((s) => el("tr", {},
      el("th", { scope: "row", class: "c-name", text: scorerName(s) }),
      el("td", { text: s.games ? record(s) : "–" }), el("td", { text: rate(s) }),
      el("td", { text: fixed(s.log_loss, 3) }), el("td", { class: "c-extra", text: fixed(s.brier, 3) }),
      el("td", { class: "c-extra", text: s.margin_error == null ? "–" : `${s.margin_error.toFixed(1)} pts` }))))));
}

async function liveSection(sb, season, index) {
  const s = sb.seasons[season];
  const champ = s.totals.find((t) => t.scorer === sb.champion.model && t.version === sb.champion.version);
  // challengers log picks too, but only the champion and the market show
  const market = s.totals.find((t) => t.scorer === "market");
  const closing = s.totals.find((t) => t.scorer === "closing");
  const tile = (label, value, sub) => el("div", {}, el("dt", { text: label }), el("dd", {}, value), el("p", { class: "sub", text: sub }));
  const gap = champ?.log_loss != null && closing?.log_loss != null ? champ.log_loss - closing.log_loss : null;
  const weeks = s.weeks.map((w) => w.week);
  const totalsCard = card(`${season} live picks`, `${s.weeks.length} week${s.weeks.length > 1 ? "s" : ""} graded`,
    el("dl", { class: "stat-strip" },
      tile("Elo", champ ? record(champ) : "–", champ ? `${rate(champ)} of winners` : ""),
      tile("Market at lock", market?.games ? record(market) : "–", market?.games ? `${rate(market)} of winners` : "no lines"),
      tile("Log loss vs closing", gap == null ? "–" : `${gap > 0 ? "+" : gap < 0 ? "−" : ""}${Math.abs(gap).toFixed(3)}`,
        gap == null ? "" : gap > 0 ? "Elo behind the closing line" : "Elo ahead of the closing line")),
    el("div", { class: "card-body" }, scoreTable([champ, market, closing].filter(Boolean), `${season} live picks, every scorer`)));

  // Week by week, with running totals.
  const weekRows = s.weeks.map((w) => {
    const rows = s.by_week[String(w.week)];
    const pick = (k, v) => rows.find((r) => r.scorer === k && (v === undefined || r.version === v));
    return { w, elo: pick(sb.champion.model, sb.champion.version), market: pick("market"), closing: pick("closing") };
  });
  const weekCard = card("Week by week", "Loss is log loss: lower is better", el("div", { class: "card-body" }, el("div", { class: "table-scroll" }, el("table", { class: "scores" },
    el("caption", { class: "visually-hidden", text: "Each graded week: Elo and the market's winners picked and log loss" }),
    el("thead", {}, el("tr", {}, ...[["Week", "c-name"], ["Elo"], ["Market"], ["Closing", "c-extra"], ["Elo loss"], ["Closing loss"]]
      .map(([h, cls]) => el("th", { scope: "col", class: cls, text: h })))),
    el("tbody", {}, ...weekRows.map(({ w, elo, market: mk, closing: cl }) => el("tr", {},
      el("th", { scope: "row", class: "c-name", text: w.label + (w.complete ? "" : " (in progress)") }),
      el("td", { text: elo ? record(elo) : "–" }), el("td", { text: mk?.games ? record(mk) : "–" }),
      el("td", { class: "c-extra", text: cl?.games ? record(cl) : "–" }),
      el("td", { text: fixed(elo?.log_loss, 3) }), el("td", { text: fixed(cl?.log_loss, 3) }))))))));

  // Biggest misses: Elo's most confident picks that lost.
  const misses = [];
  for (const week of weeks) {
    if (!(index.results[season] || []).includes(week)) continue;
    const [picks, results] = await Promise.all([ledgerJSON(weekFile("picks", season, week)), ledgerJSON(weekFile("results", season, week))]);
    const finals = Object.fromEntries(results.games.map((r) => [r.game_id, r]));
    for (const p of picks.picks.filter((x) => x.model === sb.champion.model && x.version === sb.champion.version)) {
      const g = picks.games.find((x) => x.game_id === p.game_id);
      if (!finals[g.game_id]) continue;
      const v = gameView(g, p, finals[g.game_id]);
      if (v.eloRight === false) misses.push({ ...v, label: picks.label });
    }
  }
  misses.sort((a, b) => b.p - a.p);
  const missCard = card("Biggest misses", "Elo's most confident picks that lost", misses.length
    ? el("ul", { class: "misses" }, ...misses.slice(0, 5).map((v) => {
      const { g, final } = v;
      const loser = v.fav;
      const winScore = Math.max(final.home_score, final.away_score), loseScore = Math.min(final.home_score, final.away_score);
      return el("li", {},
        el("p", { class: "miss-prob" }, prob(v.p), el("span", { text: `${loser} to win` })),
        el("div", {}, el("p", { class: "miss-title", text: `${v.winner} beat ${loser} ${winScore}–${loseScore}` }),
          el("p", { class: "miss-detail", text: `${v.label}, ${g.away} at ${g.home}. ${v.m == null ? "No market line at lock." : `The market had ${loser} at ${prob(v.m)}.`}` })));
    }))
    : el("p", { class: "card-body empty-note", text: "No misses yet." }));
  return [totalsCard, weekCard, missCard];
}

function backtestSection(bt) {
  const [first, last] = bt.seasons;
  const head = el("div", { class: "section-head" },
    el("h2", { text: `Backtest, ${first}–${last}` }),
    el("p", { text: `Replayed after the fact, not live picks: each game sees only the games before it, and Elo's settings were picked on 2002–2014. ${bt.totals[0].games.toLocaleString("en-US")} games; ties left out.` }));
  const totals = card("Totals", `${modelName(bt.model)} v${bt.version}`,
    el("div", { class: "card-body" }, scoreTable(bt.totals, `Backtest ${first}-${last}: Elo, the closing line and always picking the home team`)));
  return [head, totals, seasonCard(bt), calibrationCard(bt)];
}

// Winners picked by season: one row per season, Elo's dot and the closing line's on a shared axis.
function seasonCard(bt) {
  const seasons = Object.keys(bt.by_season);
  const rows = seasons.map((s) => {
    const elo = bt.by_season[s].find((r) => r.scorer === bt.model);
    const closing = bt.by_season[s].find((r) => r.scorer === "closing");
    return { s, elo: elo.correct / elo.games, closing: closing.correct / closing.games };
  });
  const fig = el("figure", { class: "dotplot", role: "img",
    "aria-label": "Winners picked by season, Elo against the closing line. The table below has every value." });
  const draw = () => drawDots(fig, rows);
  new ResizeObserver(() => requestAnimationFrame(draw)).observe(fig);
  const beat = rows.filter((r) => r.elo > r.closing).map((r) => r.s);
  const legend = el("p", { class: "card-meta dot-legend" },
    el("span", { class: "dot", "aria-hidden": "true", vars: { "--series": "var(--s1)" } }), "Elo",
    el("span", { class: "dot", "aria-hidden": "true", vars: { "--series": "var(--s2)" } }), "Closing line");
  const table = el("details", { class: "table-view" },
    el("summary", {}, icon("asc"), "Show as table"),
    el("div", { class: "table-scroll" }, el("table", {},
      el("thead", {}, el("tr", {}, ...["Season", "Elo", "Closing line"].map((h) => el("th", { scope: "col", text: h })))),
      el("tbody", {}, ...rows.map((r) => el("tr", {}, el("th", { scope: "row", text: r.s }),
        el("td", { text: `${(r.elo * 100).toFixed(1)}%` }), el("td", { text: `${(r.closing * 100).toFixed(1)}%` })))))));
  return el("section", { class: "card" },
    el("div", { class: "card-head" }, el("h2", { text: "Winners picked by season" }), legend),
    el("div", { class: "card-body" }, fig,
      el("p", { class: "chart-note", text: `The closing line picks more winners most seasons, but not every one${beat.length ? ` (Elo did better in ${beat.join(", ")})` : ""}: a season of 270 games carries about three points of luck either way.` }),
      table));
}

// Drawn at the figure's own width, so the text stays 12px on a phone and on a wide screen.
function drawDots(fig, rows) {
  const W = Math.max(fig.clientWidth, 260);
  if (fig.dataset.width === String(W)) return;
  fig.dataset.width = String(W);
  const lo = 0.55, hi = 0.75;
  const rowH = 26, top = 8, left = 44, right = 12, H = top + rows.length * rowH + 26;
  const x = (v) => left + ((Math.min(Math.max(v, lo), hi) - lo) / (hi - lo)) * (W - left - right);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, "aria-hidden": "true" });
  for (let v = lo; v <= hi + 1e-9; v += 0.05) {
    svg.append(svgEl("line", { class: "gridline", x1: x(v), x2: x(v), y1: top, y2: top + rows.length * rowH }));
    const t = svgEl("text", { class: "tick", x: x(v), y: H - 6, "text-anchor": "middle" });
    t.textContent = `${Math.round(v * 100)}%`;
    svg.append(t);
  }
  rows.forEach((r, i) => {
    const y = top + i * rowH + rowH / 2;
    const t = svgEl("text", { class: "tick", x: left - 10, y: y + 4, "text-anchor": "end" });
    t.textContent = r.s;
    svg.append(t, svgEl("line", { class: "connector", x1: x(r.elo), x2: x(r.closing), y1: y, y2: y }));
    for (const [k, v, color] of [["Closing line", r.closing, "var(--s2)"], ["Elo", r.elo, "var(--s1)"]]) {
      const c = svgEl("circle", { cx: x(v), cy: y, r: 5 }, { fill: color });
      const tip = svgEl("title");
      tip.textContent = `${r.s} · ${k}: ${(v * 100).toFixed(1)}%`;
      c.append(tip);
      svg.append(c);
    }
  });
  fig.replaceChildren(svg);
}

// Calibration: when Elo gave its favorite p, how often did the favorite win?
function calibrationCard(bt) {
  const edges = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0001];
  const bins = edges.slice(0, -1).map((lo, i) => ({ lo, hi: edges[i + 1], n: 0, sum: 0, won: 0 }));
  for (const g of bt.games) {
    if (g.home_score === g.away_score) continue;
    const homeFav = g.home_win_prob >= 0.5;
    const p = homeFav ? g.home_win_prob : 1 - g.home_win_prob;
    const b = bins.find((x) => p >= x.lo && p < x.hi);
    b.n++; b.sum += p; b.won += (g.home_score > g.away_score) === homeFav ? 1 : 0;
  }
  const label = (b) => (b.hi > 1 ? `${Math.round(b.lo * 100)}%+` : `${Math.round(b.lo * 100)}–${Math.round(b.hi * 100)}%`);
  const rows = bins.filter((b) => b.n).map((b) => el("li", { "aria-label": `Elo said ${label(b)}, ${b.n} games: favorites won ${prob(b.won / b.n)}, against ${prob(b.sum / b.n)} expected.` },
    el("span", { class: "cal-bin", "aria-hidden": "true", text: label(b) }),
    el("span", { class: "cal-track", "aria-hidden": "true" },
      el("span", { class: "cal-fill", vars: { width: `${(b.won / b.n) * 100}%` } }),
      el("span", { class: "cal-expect", vars: { left: `${(b.sum / b.n) * 100}%` } })),
    el("span", { class: "cal-val", "aria-hidden": "true" }, el("b", { text: prob(b.won / b.n) }), ` of ${b.n.toLocaleString("en-US")}`)));
  const legend = el("p", { class: "card-meta pick-legend" },
    el("span", { class: "key-bar", "aria-hidden": "true" }), "Favorites won", el("span", { class: "key-tick", "aria-hidden": "true" }), "Elo expected");
  return el("section", { class: "card" },
    el("div", { class: "card-head" }, el("h2", { text: "Calibration" }), legend),
    el("div", { class: "card-body" },
      el("p", { class: "cal-intro", text: "When Elo gave its favorite this chance, how often the favorite won. Honest probabilities put each bar's end on its tick." }),
      el("ul", { class: "calibration" }, ...rows)));
}
