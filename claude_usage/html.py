import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from claude_usage.pricing import cost_for_tokens, resolve_model
from claude_usage.scanner import UsageRecord

_TOP_PROJECTS = 10


def _short_path(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def _tokens(r: UsageRecord) -> int:
    return r.input_tokens + r.output_tokens + r.cache_creation_input_tokens + r.cache_read_input_tokens


def build_dashboard_data(records: list[UsageRecord], top_n: int) -> dict:
    """Everything the dashboard page draws, as plain JSON-able data."""
    daily: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    projects: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    models: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    sessions: dict[str, dict] = {}
    mix = {"input": 0, "output": 0, "cache_write": 0, "cache_read": 0}
    unpriced = 0

    for r in records:
        cost = cost_for_tokens(
            r.model, r.input_tokens, r.output_tokens,
            r.cache_creation_input_tokens, r.cache_read_input_tokens,
        )
        if cost is None:
            unpriced += 1
            cost = 0.0
        tokens = _tokens(r)
        for bucket, key in (
            (daily, r.timestamp.date().isoformat()),
            (projects, _short_path(r.cwd)),
            (models, resolve_model(r.model)),
        ):
            bucket[key][0] += cost
            bucket[key][1] += tokens
        s = sessions.setdefault(r.session_id, {
            "id": r.session_id, "project": _short_path(r.cwd),
            "start": r.timestamp, "cost": 0.0, "tokens": 0,
        })
        s["cost"] += cost
        s["tokens"] += tokens
        s["start"] = min(s["start"], r.timestamp)
        mix["input"] += r.input_tokens
        mix["output"] += r.output_tokens
        mix["cache_write"] += r.cache_creation_input_tokens
        mix["cache_read"] += r.cache_read_input_tokens

    # Continuous day axis: quiet days show as zero instead of disappearing.
    days = []
    if daily:
        d, last = date.fromisoformat(min(daily)), date.fromisoformat(max(daily))
        while d <= last:
            cost, tokens = daily.get(d.isoformat(), (0.0, 0))
            days.append({"d": d.isoformat(), "cost": round(cost, 4), "tokens": tokens})
            d += timedelta(days=1)

    def ranked(bucket: dict, limit: int | None = None) -> list[dict]:
        rows = sorted(bucket.items(), key=lambda kv: kv[1][0], reverse=True)
        out = [{"k": k, "cost": round(v[0], 4), "tokens": v[1]} for k, v in rows[:limit]]
        rest = rows[limit:] if limit else []
        if rest:  # fold the long tail into one row rather than inventing more colors
            out.append({
                "k": f"Other ({len(rest)} projects)",
                "cost": round(sum(v[0] for _, v in rest), 4),
                "tokens": sum(v[1] for _, v in rest),
            })
        return out

    top_sessions = sorted(sessions.values(), key=lambda s: s["cost"], reverse=True)[:top_n]
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "total_cost": round(sum(v[0] for v in projects.values()), 2),
        "session_count": len(sessions),
        "unpriced": unpriced,
        "mix": mix,
        "daily": days,
        "projects": ranked(projects, _TOP_PROJECTS),
        "models": ranked(models),
        "sessions": [
            {**s, "start": s["start"].isoformat(timespec="minutes"), "cost": round(s["cost"], 4)}
            for s in top_sessions
        ],
    }


def render_dashboard(records: list[UsageRecord], top_n: int, live: bool = False) -> str:
    data = json.dumps(build_dashboard_data(records, top_n))
    # "</" would let a project path close the <script> tag early.
    page = _TEMPLATE.replace("__DATA__", data.replace("</", "<\\/"))
    return page.replace("const LIVE = false;", "const LIVE = true;") if live else page


_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claude Usage</title>
<style>
:root {
  color-scheme: light;
  --surface: #fcfcfb; --page: #f4f3f0; --card: #fcfcfb; --border: #e1e0d9;
  --text: #0b0b0b; --text-2: #52514e; --muted: #6d6b66; --grid: #e1e0d9;
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --s4: #eda100;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --surface: #1a1a19; --page: #121211; --card: #1a1a19; --border: #2c2c2a;
    --text: #ffffff; --text-2: #c3c2b7; --muted: #9a988f; --grid: #2c2c2a;
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --surface: #1a1a19; --page: #121211; --card: #1a1a19; --border: #2c2c2a;
  --text: #ffffff; --text-2: #c3c2b7; --muted: #9a988f; --grid: #2c2c2a;
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --s4: #c98500;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--text);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 16px 64px; }
header { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; flex-wrap: wrap; }
h1 { font-size: 20px; margin: 0; }
.sub { color: var(--muted); font-size: 12px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-top: 16px; }
h2 { font-size: 15px; margin: 0 0 4px; }
.hero { display: flex; gap: 40px; flex-wrap: wrap; align-items: flex-end; }
.hero .big { font-size: 52px; font-weight: 600; line-height: 1; }
.tile .label { color: var(--text-2); font-size: 12px; }
.tile .value { font-size: 22px; font-weight: 600; }
.grid2 { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; }
.grid2 .card { margin-top: 0; }
@media (max-width: 760px) { .grid2 { grid-template-columns: minmax(0, 1fr); } .hero .big { font-size: 40px; } }
svg text { fill: var(--muted); font-size: 11px; }
.bars { display: grid; grid-template-columns: minmax(0, 1fr) 72px; gap: 6px 12px; margin-top: 12px; align-items: center; }
.bars .name { font-size: 12px; color: var(--text-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bars .val { font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }
.bars .track { grid-column: 1 / -1; height: 10px; margin-top: -4px; }
.bars .fill { height: 10px; background: var(--s1); border-radius: 0 4px 4px 0; min-width: 2px; }
.stack { display: flex; gap: 2px; height: 24px; margin: 14px 0 12px; }
.stack div { border-radius: 0; }
.stack div:first-child { border-radius: 4px 0 0 4px; } .stack div:last-child { border-radius: 0 4px 4px 0; }
.legend { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 6px 16px; font-size: 12px; color: var(--text-2); }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }
th { text-align: left; color: var(--muted); font-weight: 500; border-bottom: 1px solid var(--border); padding: 6px 8px 6px 0; }
td { border-bottom: 1px solid var(--border); padding: 6px 8px 6px 0; color: var(--text-2); white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
td.mono { font-family: ui-monospace, Menlo, monospace; }
.scroll { overflow-x: auto; }
#tip { position: fixed; pointer-events: none; background: var(--text); color: var(--surface);
  font-size: 12px; padding: 6px 8px; border-radius: 6px; display: none; white-space: nowrap; z-index: 9; }
details { margin-top: 12px; font-size: 12px; color: var(--text-2); }
.note { color: var(--muted); font-size: 12px; margin-top: 8px; }
button.theme { background: none; border: 1px solid var(--border); color: var(--text-2); border-radius: 6px; padding: 4px 10px; cursor: pointer; }
</style>
</head>
<body>
<main>
  <header>
    <div><h1>Claude Code usage</h1><div class="sub" id="gen"></div></div>
    <button class="theme" id="theme">Toggle theme</button>
  </header>

  <section class="card hero">
    <div><div class="tile label">Estimated cost (API list prices)</div><div class="big" id="total"></div></div>
    <div class="tile"><div class="label">Tokens</div><div class="value" id="tokens"></div></div>
    <div class="tile"><div class="label">Sessions</div><div class="value" id="sessions"></div></div>
    <div class="tile"><div class="label">Busiest day</div><div class="value" id="peak"></div></div>
  </section>

  <section class="card">
    <h2>Cost per day</h2>
    <div class="sub">Hover a column for the exact value</div>
    <svg id="daily" width="100%" height="240" role="img" aria-label="Daily cost column chart"></svg>
    <details><summary>Show as table</summary><div class="scroll"><table id="dailyTable"></table></div></details>
  </section>

  <div class="grid2" style="margin-top:16px">
    <section class="card"><h2>Cost by project</h2><div class="bars" id="projects"></div></section>
    <section class="card"><h2>Cost by model</h2><div class="bars" id="models"></div></section>
  </div>

  <section class="card">
    <h2>Where the tokens go</h2>
    <div class="sub">Share of all tokens by type</div>
    <div class="stack" id="mix"></div>
    <div class="legend" id="mixLegend"></div>
  </section>

  <section class="card">
    <h2>Most expensive sessions</h2>
    <div class="scroll"><table id="top"></table></div>
  </section>
  <div class="note" id="unpriced"></div>
</main>
<div id="tip"></div>
<script>
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const usd = v => "$" + v.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
const compact = v => Intl.NumberFormat(undefined, {notation: "compact", maximumFractionDigits: 1}).format(v);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const tip = $("tip");
function showTip(e, html) { tip.innerHTML = html; tip.style.display = "block";
  const x = Math.min(e.clientX + 12, innerWidth - tip.offsetWidth - 8);
  tip.style.left = x + "px"; tip.style.top = (e.clientY - tip.offsetHeight - 10) + "px"; }
const hideTip = () => tip.style.display = "none";

const LIVE = false;
try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch (e) {}
$("theme").onclick = () => {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const cur = document.documentElement.dataset.theme || (dark ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch (e) {}
};
// Served by `claude-usage serve`: reload when any session log changes.
if (LIVE) {
  let seen = null;
  setInterval(async () => {
    try {
      const v = await (await fetch("/version", {cache: "no-store"})).text();
      if (seen !== null && v !== seen) location.reload();
      seen = v;
    } catch (e) {}
  }, 15000);
}

$("gen").textContent = (LIVE ? "Live · refreshes when a session changes · " : "Generated ") + DATA.generated.replace("T", " ") + " UTC from local session logs";
$("total").textContent = usd(DATA.total_cost);
const m = DATA.mix, totalTokens = m.input + m.output + m.cache_write + m.cache_read;
$("tokens").textContent = compact(totalTokens);
$("sessions").textContent = DATA.session_count.toLocaleString();
const peak = DATA.daily.reduce((a, b) => b.cost > a.cost ? b : a, {cost: 0, d: "-"});
$("peak").textContent = peak.d === "-" ? "-" : usd(peak.cost) + " · " + peak.d.slice(5);

// Daily columns: single series, so no legend - the title names it.
function drawDaily() {
  const svg = $("daily"), W = svg.clientWidth || 800, H = 240, L = 48, R = 8, T = 12, B = 28;
  const days = DATA.daily, n = days.length || 1;
  const max = Math.max(...days.map(d => d.cost), 1);
  const step = Math.pow(10, Math.floor(Math.log10(max))), nice = Math.ceil(max / step) * step;
  const y = v => T + (H - T - B) * (1 - v / nice);
  const band = (W - L - R) / n, bw = Math.max(1, Math.min(24, band - 2));
  let s = "";
  for (let i = 0; i <= 4; i++) {
    const v = nice * i / 4, yy = y(v);
    s += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--grid)" stroke-width="1"/>`;
    s += `<text x="${L - 6}" y="${yy + 4}" text-anchor="end">$${compact(v)}</text>`;
  }
  const every = Math.ceil(n / Math.max(1, Math.floor((W - L - R) / 56)));
  days.forEach((d, i) => {
    const x = L + i * band + (band - bw) / 2, h = y(0) - y(d.cost), r = Math.min(4, bw / 2, h);
    if (h > 0) s += `<path d="M${x},${y(0)} v${-(h - r)} q0,${-r} ${r},${-r} h${bw - 2 * r} q${r},0 ${r},${r} v${h - r} z" fill="var(--s1)"/>`;
    s += `<rect class="hit" data-i="${i}" x="${L + i * band}" y="${T}" width="${band}" height="${H - T - B}" fill="transparent"/>`;
    if (i % every === 0) s += `<text x="${L + i * band + band / 2}" y="${H - 8}" text-anchor="middle">${d.d.slice(5)}</text>`;
  });
  svg.innerHTML = s;
  svg.querySelectorAll(".hit").forEach(el => {
    el.onmousemove = e => { const d = days[+el.dataset.i];
      el.setAttribute("fill", "var(--grid)"); el.setAttribute("fill-opacity", ".5");
      showTip(e, `<b>${d.d}</b><br>${usd(d.cost)} · ${compact(d.tokens)} tokens`); };
    el.onmouseleave = () => { el.setAttribute("fill", "transparent"); hideTip(); };
  });
}
drawDaily();
addEventListener("resize", drawDaily);
$("dailyTable").innerHTML = "<tr><th>Date</th><th class=num>Cost</th><th class=num>Tokens</th></tr>" +
  DATA.daily.slice().reverse().map(d => `<tr><td>${d.d}</td><td class=num>${usd(d.cost)}</td><td class=num>${compact(d.tokens)}</td></tr>`).join("");

function bars(el, rows) {
  const max = Math.max(...rows.map(r => r.cost), 0.0001);
  el.innerHTML = rows.map(r => `<div class="name" title="${esc(r.k)}">${esc(r.k)}</div><div class="val">${usd(r.cost)}</div>
    <div class="track" title="${esc(r.k)}: ${usd(r.cost)} · ${compact(r.tokens)} tokens"><div class="fill" style="width:${(r.cost / max * 100).toFixed(2)}%"></div></div>`).join("");
}
bars($("projects"), DATA.projects);
bars($("models"), DATA.models);

const parts = [["Input", m.input, "--s1"], ["Output", m.output, "--s2"], ["Cache write", m.cache_write, "--s3"], ["Cache read", m.cache_read, "--s4"]];
$("mix").innerHTML = parts.filter(p => p[1] > 0).map(p =>
  `<div style="flex:${p[1]} 0 2px;background:var(${p[2]})" title="${p[0]}: ${compact(p[1])}"></div>`).join("");
$("mixLegend").innerHTML = parts.map(p =>
  `<div><span class="sw" style="background:var(${p[2]})"></span>${p[0]} <b style="color:var(--text)">${compact(p[1])}</b> · ${(p[1] / (totalTokens || 1) * 100).toFixed(1)}%</div>`).join("");

$("top").innerHTML = "<tr><th>Started</th><th>Project</th><th>Session</th><th class=num>Tokens</th><th class=num>Cost</th></tr>" +
  DATA.sessions.map(s => `<tr><td>${s.start.slice(0, 16).replace("T", " ")}</td><td>${esc(s.project)}</td>
    <td class=mono>${esc(s.id.slice(0, 8))}</td><td class=num>${compact(s.tokens)}</td><td class=num>${usd(s.cost)}</td></tr>`).join("");

if (DATA.unpriced) $("unpriced").textContent = DATA.unpriced + " record(s) use a model not in the price table and are counted as $0.";
</script>
</body>
</html>
"""
