// Award Watch: reads the JSON in ../predictions/ and renders the race list and the share-by-week chart.
"use strict";

const DATA = "../predictions/";
const AWARD_NAMES = { mvp: "MVP", opoy: "Offensive Player of the Year" };
const SERIES = ["--s1", "--s2", "--s3", "--s4", "--s5"]; // fixed order; color follows the player, not the rank
const SVG_NS = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);
const pct = (x) => `${(x * 100).toFixed(1)}%`;

// Small DOM helpers. Text always goes in through textContent: names come from data files.
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "vars") for (const [name, v] of Object.entries(value)) node.style.setProperty(name, v);
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}
function svgEl(tag, attrs = {}, style = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  Object.assign(node.style, style);
  return node;
}
function icon(kind) {
  const paths = { up: "M5 1.5 9 7.5H1z", down: "M5 8.5 1 2.5h8z", same: "M1.5 4.25h7v1.5h-7z" };
  const s = svgEl("svg", { viewBox: "0 0 10 10", "aria-hidden": "true" });
  s.append(svgEl("path", { d: paths[kind], fill: "currentColor" }));
  return s;
}
function lastName(name) {
  const parts = name.split(" ").filter((p) => !/^(Jr\.?|Sr\.?|II|III|IV|V)$/.test(p));
  const n = parts.length;
  return n > 2 && parts[n - 2] === "St." ? `St. ${parts[n - 1]}` : parts[n - 1];
}

async function getJSON(path) {
  const res = await fetch(DATA + path, { cache: "no-cache" });
  if (!res.ok) throw Object.assign(new Error(`${path}: HTTP ${res.status}`), { status: res.status });
  return res.json();
}

function showMessage(text) {
  $("content").hidden = true;
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
  $("status").replaceChildren(`${latest.season} season · Through week ${latest.through_week}`,
    el("span", { class: "updated", text: ` · Updated ${updated}` }));

  // The chart needs every week of the season. If those fail, the list still renders.
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
    text: AWARD_NAMES[award] || award.toUpperCase(),
  }));
  $("tabs").replaceChildren(...tabs);

  function select(i) {
    tabs.forEach((tab, j) => {
      tab.setAttribute("aria-selected", String(i === j));
      tab.tabIndex = i === j ? 0 : -1;
    });
    $("panel").setAttribute("aria-labelledby", tabs[i].id);
    render(awards[i], latest, teams, weeks);
  }
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
  select(0);
}

function render(award, latest, teams, weeks) {
  const name = AWARD_NAMES[award] || award.toUpperCase();
  const rows = latest.awards[award] || [];
  $("title").textContent = `${name} race`;
  document.title = `Award Watch: NFL ${name} race`;
  $("lede").textContent = `The model's predicted share of the AP ${name} vote, from stats through week ${latest.through_week}.`;
  $("panel").setAttribute("aria-busy", "false");
  if (!rows.length) {
    showMessage(`No ${name} predictions in this week's file yet.`);
    return;
  }
  const top = rows.slice(0, SERIES.length);
  $("race-list").replaceChildren(...rows.map((row, i) => raceRow(row, teams[row.team] || {}, i < top.length ? SERIES[i] : null)));
  renderTrend(award, top, weeks);
}

function raceRow(r, team, seriesVar) {
  let move;
  if (r.prev_rank == null) {
    move = el("span", { class: "move new", text: "New" }, el("span", { class: "visually-hidden", text: " in the top 10 this week" }));
  } else {
    const diff = r.prev_rank - r.rank;
    const kind = diff > 0 ? "up" : diff < 0 ? "down" : "same";
    const words = diff === 0 ? "No change since last week" : `${kind === "up" ? "Up" : "Down"} ${Math.abs(diff)} since last week`;
    move = el("span", { class: `move ${kind}`, title: words }, icon(kind),
      el("span", { "aria-hidden": "true", text: diff === 0 ? "" : String(Math.abs(diff)) }),
      el("span", { class: "visually-hidden", text: words }));
  }

  const avatar = el("div", { class: "avatar", vars: team.color ? { "--team": team.color } : {} });
  if (r.headshot_url) {
    const img = el("img", { src: smallHeadshot(r.headshot_url), alt: "", width: "48", height: "48", decoding: "async" });
    img.addEventListener("error", () => img.replaceWith(initials(r.player)), { once: true });
    avatar.append(img);
  } else {
    avatar.append(initials(r.player));
  }

  const nameLine = el("p", { class: "name" });
  if (seriesVar) nameLine.append(el("span", { class: "key", "aria-hidden": "true", vars: { "--series": `var(${seriesVar})` } }));
  nameLine.append(el("span", { class: "name-text", text: r.player }));

  const meta = el("p", { class: "meta" });
  if (team.logo) meta.append(el("img", { src: team.logo, alt: "", width: "18", height: "18" }));
  meta.append(el("span", { text: `${r.position} · ${r.team} · ${r.team_record}`, title: team.name || r.team }));

  const s = r.stats;
  const parts = [`${s.yards_per_game.toFixed(1)} yds/g`, `${s.tds} TD`, `${s.turnovers} TO`, `${s.epa_per_game.toFixed(1)} EPA/g`];
  // Each stat is its own span so a narrow screen wraps between stats, never inside one.
  const stats = el("p", { class: "stats" }, ...parts.flatMap((t, i) => [i ? " · " : "", el("span", { text: t })]));

  const share = el("div", { class: "share" },
    el("span", { class: "pct", text: pct(r.share) }),
    el("span", { class: "meter", "aria-hidden": "true" }, el("span", { vars: { width: `${Math.max(r.share * 100, 0)}%` } })),
    el("span", { class: "was", text: r.prev_share == null ? "" : `was ${pct(r.prev_share)}` }));

  return el("li", { class: "row" },
    el("div", { class: "pos" }, el("span", { class: "rank", text: String(r.rank) }), move),
    avatar, el("div", { class: "who" }, nameLine, meta, stats), share);
}

// NFL headshots are multi-megabyte originals. Their image CDN resizes on request, so ask for a
// 96px face crop (2x the 48px avatar); any URL in another shape is used as is.
function smallHeadshot(url) {
  return url.replace("/image/upload/f_auto,q_auto/", "/image/upload/f_auto,q_auto,c_thumb,g_face,w_96,h_96/");
}

function initials(name) {
  const letters = name.split(" ").filter(Boolean).map((p) => p[0]).slice(0, 2).join("");
  return el("span", { class: "initials", "aria-hidden": "true", text: letters });
}

// ---------- Share-by-week chart ----------

let redraw = null;
new ResizeObserver(() => redraw && requestAnimationFrame(redraw)).observe($("chart"));

function renderTrend(award, top, weeks) {
  const chart = $("chart");
  if (!weeks.length) {
    chart.replaceChildren(el("p", { class: "trend-note", text: "The week-by-week files didn't load, so there's no trend to show." }));
    $("legend").replaceChildren();
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

  $("legend").replaceChildren(...series.map((s) => el("li", {},
    el("span", { class: "key", "aria-hidden": "true", vars: { "--series": s.color } }), el("span", { text: s.name }))));
  renderTable(series, xWeeks);

  redraw = () => drawChart(chart, series, xWeeks);
  redraw();
}

function niceScale(max) {
  const step = [0.05, 0.1, 0.2, 0.25].find((s) => max / s <= 5) || 0.25;
  return { step, top: Math.max(step, Math.ceil(max / step) * step) };
}

function drawChart(box, series, xWeeks) {
  const W = Math.max(box.clientWidth, 280);
  const H = Math.round(Math.min(320, Math.max(220, W * 0.62)));
  const m = { top: 10, right: 76, bottom: 28, left: 40 };
  const iw = W - m.left - m.right;
  const ih = H - m.top - m.bottom;
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  const { step, top } = niceScale(Math.max(...all, 0.05));
  const n = xWeeks.length;
  const xAt = (i) => m.left + (n === 1 ? iw / 2 : (i * iw) / (n - 1));
  const yAt = (v) => m.top + ih - (v / top) * ih;

  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, "aria-hidden": "true" });

  // Recessive grid: hairlines at each y tick, a slightly darker baseline at zero.
  const grid = svgEl("g", { class: "grid" });
  for (let v = step; v <= top + 1e-9; v += step) {
    grid.append(svgEl("line", { x1: m.left, x2: m.left + iw, y1: yAt(v), y2: yAt(v) }));
  }
  svg.append(grid, svgEl("line", { class: "baseline", x1: m.left, x2: m.left + iw, y1: yAt(0), y2: yAt(0) }));
  for (let v = 0; v <= top + 1e-9; v += step) {
    const t = svgEl("text", { class: "tick", x: m.left - 8, y: yAt(v) + 4, "text-anchor": "end" });
    t.textContent = `${Math.round(v * 100)}%`;
    svg.append(t);
  }
  const every = iw / Math.max(n - 1, 1) < 26 ? 2 : 1; // thin the week labels when they'd crowd
  xWeeks.forEach((w, i) => {
    if ((n - 1 - i) % every) return;
    const t = svgEl("text", { class: "tick", x: xAt(i), y: H - 8, "text-anchor": "middle" });
    t.textContent = String(w);
    svg.append(t);
  });
  const wk = svgEl("text", { class: "tick", x: m.left - 8, y: H - 8, "text-anchor": "end" });
  wk.textContent = "Wk";
  svg.append(wk);

  // Lines, broken where a player was outside the top 10, with a ringed dot at each line's end.
  const labels = [];
  for (const s of series) {
    const g = svgEl("g", { class: "series" });
    let d = "";
    let prev = null;
    s.values.forEach((v, i) => {
      if (v == null) { prev = null; return; }
      d += `${prev == null ? "M" : "L"}${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`;
      const isolated = prev == null && s.values[i + 1] == null && i !== n - 1;
      if (isolated) g.append(svgEl("circle", { cx: xAt(i), cy: yAt(v), r: 3 }, { fill: s.color }));
      prev = v;
    });
    g.append(svgEl("path", { d }, { stroke: s.color }));
    const last = s.values.at(-1);
    if (last != null) {
      g.append(svgEl("circle", { cx: xAt(n - 1), cy: yAt(last), r: 4 }, { fill: s.color }));
      labels.push({ y: yAt(last), text: s.label });
    }
    svg.append(g);
  }

  // Direct end labels, only where they don't collide; the legend and tooltip cover the rest.
  labels.sort((a, b) => a.y - b.y);
  let lastY = -Infinity;
  for (const l of labels) {
    if (l.y - lastY < 14) continue;
    const t = svgEl("text", { class: "end-label", x: xAt(n - 1) + 9, y: l.y + 4 });
    t.textContent = l.text;
    svg.append(t);
    lastY = l.y;
  }

  // Hover layer: a crosshair that snaps to the nearest week, one tooltip listing every series.
  const cross = svgEl("line", { class: "crosshair", y1: m.top, y2: m.top + ih, visibility: "hidden" });
  const hoverDots = svgEl("g", { class: "series" });
  const hit = svgEl("rect", { x: m.left - 12, y: 0, width: iw + 24, height: H, fill: "transparent" });
  svg.append(cross, hoverDots, hit);

  const tip = el("div", { class: "tooltip", hidden: "" });
  const live = el("p", { class: "visually-hidden", "aria-live": "polite" });
  box.replaceChildren(svg, tip, live);
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

    const ranked = [...series].sort((a, b) => (b.values[i] ?? -1) - (a.values[i] ?? -1));
    tip.replaceChildren(el("p", { class: "tooltip-title", text: `Week ${xWeeks[i]}` }),
      ...ranked.map((s) => el("p", { class: "tooltip-row" },
        el("span", { class: "key", "aria-hidden": "true", vars: { "--series": s.color } }),
        el("strong", { text: s.values[i] == null ? "–" : pct(s.values[i]) }),
        el("span", { text: s.label }))));
    tip.hidden = false;
    const scale = box.clientWidth / W;
    const left = x * scale + 14;
    tip.style.left = `${left + tip.offsetWidth > box.clientWidth ? x * scale - tip.offsetWidth - 14 : left}px`;
    if (announce) {
      live.textContent = `Week ${xWeeks[i]}: ` + ranked.map((s) =>
        `${s.name} ${s.values[i] == null ? "outside the top 10" : pct(s.values[i])}`).join(", ");
    }
  }
  function hide() {
    current = null;
    cross.setAttribute("visibility", "hidden");
    hoverDots.replaceChildren();
    tip.hidden = true;
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
    const moves = { ArrowLeft: -1, ArrowRight: 1, Home: -n, End: n };
    if (e.key === "Escape") return hide();
    if (!(e.key in moves)) return;
    e.preventDefault();
    show(Math.min(n - 1, Math.max(0, (current ?? n - 1) + moves[e.key])), true);
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

main();
