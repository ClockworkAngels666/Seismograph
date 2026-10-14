"""Interactive 3D risk globe (WebGL, via the globe.gl library) as a Streamlit custom component.

Drag to rotate, scroll / pinch or the +/− buttons to zoom, click a country (or a small-state dot) to
see its index in a side panel. Layers: countries coloured and raised by risk, pulsing rings where
battle deaths are high, animated arcs for the largest refugee flows, and a year slider that replays
the index since config.HISTORY_START. The selected country is sent back to Python (for the news
feed), and "Open full profile" sends a one-off trigger.

The library, the Natural Earth outlines and the flags load from jsDelivr in the visitor's browser,
pinned to exact versions so an upstream release can't change the app.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config

GLOBE_JS_URL = "https://cdn.jsdelivr.net/npm/globe.gl@2.46.2/dist/globe.gl.min.js"
COUNTRIES_URL = (
    "https://cdn.jsdelivr.net/gh/vasturiano/globe.gl@v2.46.2/example/datasets/ne_110m_admin_0_countries.geojson"
)
HEIGHT = 640
MOBILE_HEIGHT = 520
OUT_OF_VIEW_COLOR = "#1b1b1a"  # countries outside the current region / income filter
TOP_FLOWS = 40  # largest refugee flows drawn when no country is selected
CONFLICT_THRESHOLD = 25  # UCDP: 25 battle deaths a year = active armed conflict

_HTML = """
<div class="rg-wrap">
  <div class="rg-canvas"></div>
  <div class="rg-status">Loading the 3D globe…</div>
  <div class="rg-controls">
    <button data-act="in" title="Zoom in">+</button>
    <button data-act="out" title="Zoom out">−</button>
    <button data-act="reset" title="Reset the view">Reset</button>
    <button data-act="spin" title="Turn auto-rotation on or off">Spin</button>
    <button data-act="extrude" title="Raise each country by its risk score">3D</button>
    <button data-act="flows" title="Show the largest refugee flows (origin → host)">Flows</button>
    <button data-act="conflict" title="Pulse where battle deaths are high (≥ 25 a year)">Conflict</button>
  </div>
  <div class="rg-hint">Drag to rotate · scroll, pinch or +/− to zoom · click a country</div>
  <div class="rg-legend">
    <div class="rg-legend-title"></div>
    <div class="rg-legend-bar"></div>
    <div class="rg-legend-ticks"><span>0 · lower</span><span>50</span><span>higher · 100</span></div>
    <div class="rg-legend-keys"></div>
  </div>
  <div class="rg-time">
    <button class="rg-play" title="Replay the index year by year">▶</button>
    <input class="rg-year-input" type="range" min="0" max="0" value="0" step="1" aria-label="Year">
    <span class="rg-year"></span>
  </div>
  <div class="rg-panel" hidden></div>
</div>
"""

_CSS = """
.rg-wrap { position: relative; width: 100%; height: 640px; border-radius: 14px; overflow: hidden;
  background: radial-gradient(ellipse at 50% 45%, #0c1f3f 0%, #050b16 45%, #000 75%);
  border: 1px solid #1f1f1e; font-family: inherit; color: #ececec; }
.rg-canvas { position: absolute; inset: 0; cursor: grab; }
.rg-status { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  padding: 24px; text-align: center; color: #898781; font-size: 0.85rem; }
.rg-status[hidden], .rg-panel[hidden] { display: none; }
.rg-controls { position: absolute; top: 12px; left: 12px; z-index: 2; display: flex; flex-direction: column; gap: 6px; }
.rg-controls button, .rg-play { font: inherit; font-size: 0.78rem; min-width: 44px; height: 32px; padding: 0 10px;
  cursor: pointer; background: rgba(20,20,20,0.85); color: #ececec; border: 1px solid #383835; border-radius: 8px; }
.rg-controls button:hover, .rg-play:hover { border-color: #3987e5; }
.rg-controls button.on { background: #3987e5; border-color: #3987e5; color: #000; font-weight: 600; }
.rg-hint { position: absolute; top: 14px; right: 14px; left: 100px; z-index: 1; color: #898781; font-size: 0.7rem;
  text-align: right; pointer-events: none; }
.rg-legend { position: absolute; left: 12px; bottom: 12px; z-index: 2; width: 240px; padding: 8px 10px;
  background: rgba(10,10,10,0.82); border: 1px solid #2c2c2a; border-radius: 8px; font-size: 0.7rem; }
.rg-legend-bar { height: 8px; border-radius: 4px; margin: 6px 0 4px; }
.rg-legend-ticks { display: flex; justify-content: space-between; color: #898781; }
.rg-legend-keys { margin-top: 6px; color: #c3c2b7; line-height: 1.5; }
.rg-legend-keys i { display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px;
  vertical-align: -1px; }
.rg-time { position: absolute; left: 266px; right: 12px; bottom: 12px; z-index: 2; display: flex; align-items: center;
  gap: 10px; padding: 8px 12px; background: rgba(10,10,10,0.82); border: 1px solid #2c2c2a; border-radius: 8px; }
.rg-time[hidden] { display: none; }
.rg-time input { flex: 1; accent-color: #3987e5; min-width: 60px; }
.rg-custom { margin-top: 10px; font-size: 0.85rem; }
.rg-custom b { font-size: 1.05rem; }
.rg-year { font-weight: 700; min-width: 3.2em; text-align: right; }
.rg-panel { position: absolute; top: 12px; right: 12px; z-index: 3; width: 300px; max-height: calc(100% - 84px);
  overflow: auto; padding: 14px 16px; background: rgba(12,12,12,0.95); border: 1px solid #383835;
  border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,0.6); }
.rg-close { position: absolute; top: 6px; right: 8px; background: none; border: 0; color: #898781;
  font-size: 1.3rem; cursor: pointer; }
.rg-name { display: flex; align-items: center; gap: 8px; font-size: 1.1rem; font-weight: 700; padding-right: 22px; }
.rg-name img { height: 1.05em; aspect-ratio: 4 / 3; border-radius: 3px; box-shadow: 0 0 0 1px #2c2c2a; }
.rg-sub { color: #898781; font-size: 0.75rem; margin-top: 2px; }
.rg-score { display: flex; align-items: baseline; gap: 6px; margin-top: 10px; }
.rg-big { font-size: 2.4rem; font-weight: 700; line-height: 1; }
.rg-of { color: #898781; }
.rg-delta { font-size: 0.8rem; }
.rg-badge { margin-left: auto; padding: 3px 10px; border-radius: 999px; font-weight: 600; font-size: 0.75rem; }
.rg-rank { font-size: 0.78rem; margin-top: 6px; }
.rg-rank span, .rg-tip span, .rg-muted { color: #898781; }
.rg-spark { margin-top: 10px; }
.rg-spark svg { display: block; width: 100%; height: 54px; }
.rg-section { margin-top: 12px; font-size: 0.7rem; color: #898781; text-transform: uppercase; letter-spacing: 0.04em; }
.rg-pillars { margin-top: 6px; display: grid; gap: 6px; }
.rg-prow { display: grid; grid-template-columns: 92px 1fr 30px; align-items: center; gap: 8px;
  font-size: 0.75rem; color: #c3c2b7; }
.rg-prow.rg-active { color: #ffffff; font-weight: 700; }
.rg-ptrack { height: 8px; background: #262624; border-radius: 4px; overflow: hidden; }
.rg-pbar { display: block; height: 100%; border-radius: 4px; }
.rg-pval { text-align: right; }
.rg-flags { margin-top: 10px; font-size: 0.75rem; color: #fd8078; }
.rg-flags.ok { color: #5ac698; }
.rg-note { color: #c3c2b7; font-size: 0.8rem; }
.rg-open { margin-top: 12px; width: 100%; font: inherit; font-size: 0.8rem; font-weight: 600; padding: 8px;
  background: #3987e5; color: #000; border: 0; border-radius: 8px; cursor: pointer; }
.rg-tip { font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 12px; line-height: 1.45; }
@media (max-width: 640px) {
  .rg-wrap { height: var(--rg-mobile-h, 520px) !important; }
  .rg-hint { display: none; }
  .rg-controls { flex-direction: row; flex-wrap: wrap; right: 12px; gap: 4px; }
  .rg-controls button { min-width: 36px; height: 30px; padding: 0 8px; font-size: 0.72rem; }
  .rg-legend { left: 12px; right: 12px; width: auto; bottom: 62px; padding: 6px 8px; }
  .rg-legend-keys { display: none; }
  .rg-time { left: 12px; right: 12px; }
  .rg-panel { left: 8px; right: 8px; top: auto; bottom: 8px; width: auto; max-height: 72%; }
}
"""

_JS = """
const GLOBE_JS = "__GLOBE_JS__";
const COUNTRIES = "__COUNTRIES__";
// Natural Earth codes that differ from the World Bank's (Somaliland is shown as part of Somalia)
const CODE_FIX = { CYN: "CYP", KOS: "XKX", SOL: "SOM" };
let libraryPromise = null;
let countriesPromise = null;
const lastViews = {};  // per globe (component key): the camera survives Streamlit re-mounting it

function loadLibrary() {
  if (window.Globe) return Promise.resolve(window.Globe);
  if (!libraryPromise) {
    libraryPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = GLOBE_JS;
      script.async = true;
      script.onload = () => resolve(window.Globe);
      script.onerror = () => { libraryPromise = null; reject(new Error("the 3D library could not be downloaded")); };
      document.head.appendChild(script);
    });
  }
  return libraryPromise;
}

function centreOf(geometry) {
  // Bounding-box centre of the largest ring: good enough to point the camera at a country
  const polygons = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.coordinates;
  let ring = polygons[0][0];
  for (const polygon of polygons) if (polygon[0].length > ring.length) ring = polygon[0];
  let minX = 180, maxX = -180, minY = 90, maxY = -90;
  for (const [x, y] of ring) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x); minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return { lng: (minX + maxX) / 2, lat: (minY + maxY) / 2 };
}

function loadCountries() {
  if (!countriesPromise) {
    countriesPromise = fetch(COUNTRIES)
      .then((r) => { if (!r.ok) throw new Error("country shapes: HTTP " + r.status); return r.json(); })
      .then((geojson) => geojson.features
        .map((f) => {
          const p = f.properties;
          const code = /^[A-Z]{3}$/.test(p.ISO_A3) ? p.ISO_A3 : p.ADM0_A3;
          f.iso3 = CODE_FIX[code] || code;
          f.centre = centreOf(f.geometry);
          return f;
        })
        .filter((f) => f.iso3 !== "ATA"))
      .catch((err) => { countriesPromise = null; throw err; });
  }
  return countriesPromise;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function colourAt(scale, t) {
  t = Math.max(0, Math.min(1, t));
  for (let i = 1; i < scale.length; i++) {
    const [t1, c1] = scale[i];
    if (t <= t1) {
      const [t0, c0] = scale[i - 1];
      const k = t1 > t0 ? (t - t0) / (t1 - t0) : 0;
      const a = hexToRgb(c0), b = hexToRgb(c1);
      return "rgb(" + a.map((v, j) => Math.round(v + (b[j] - v) * k)).join(",") + ")";
    }
  }
  return scale[scale.length - 1][1];
}

function fmtPeople(n) {
  if (n >= 1e6) return (n / 1e6).toFixed(1) + " m";
  if (n >= 1e3) return Math.round(n / 1e3) + " k";
  return String(Math.round(n));
}

// ---- data helpers --------------------------------------------------------------
// A globe either colours by the index (history arrays, with the year slider) or by a custom
// current value per country (data.custom: e.g. change since last year, days to the next election).
const isLatest = (ctx) => ctx.yearIndex === ctx.data.years.length - 1;
function valueOf(ctx, c) {
  if (ctx.data.custom) return c.custom ?? null;
  return c.value ? c.value[ctx.yearIndex] : c.composite[ctx.yearIndex];
}
function norm(ctx, v) {
  const [lo, hi] = ctx.data.range;
  return hi > lo ? (v - lo) / (hi - lo) : 0;
}
function fmtValue(ctx, v) {
  const f = ctx.data.valueFormat;
  if (f === "signed") return (v > 0 ? "+" : "") + v.toFixed(1);
  if (f === "days") return v <= 0 ? "today" : "in " + Math.round(v) + " days";
  if (f === "score") return v.toFixed(0) + "/100";
  return v.toFixed(1);
}
function tierFor(ctx, score) {
  if (score == null) return null;
  let tier = ctx.data.tierList[0];
  for (const t of ctx.data.tierList) if (score >= t.lower) tier = t;
  return tier;
}
function locate(ctx, iso3) {
  const f = ctx.featureByIso.get(iso3);
  if (f) return f.centre;
  const c = ctx.byIso.get(iso3);
  return c && c.lat != null && c.lng != null ? { lat: c.lat, lng: c.lng } : null;
}

function startView(ctx) {
  const data = ctx.data;
  const at = data.focus && ctx.featureByIso ? locate(ctx, data.focus) : null;
  if (at) return { lat: at.lat, lng: at.lng, altitude: 1.9 };
  if (data.centre) return { lng: data.centre[0], lat: data.centre[1], altitude: 1.6 };
  return { lng: 20, lat: 15, altitude: 2.3 };
}

function colourFor(ctx, c) {
  if (!c) return ctx.data.noData;
  const v = valueOf(ctx, c);
  if (v == null) return ctx.data.noData;
  if (!c.inView) return ctx.data.outOfView;
  return colourAt(ctx.data.colorscale, norm(ctx, v));
}

function heightFor(ctx, iso3, base) {
  const c = ctx.byIso.get(iso3);
  const v = c ? valueOf(ctx, c) : null;
  let h = base;
  if (ctx.extrude && c && c.inView && v != null) {
    const [lo, hi] = ctx.data.range;
    const t = ctx.data.extrudeAbs ? Math.abs(v) / Math.max(Math.abs(lo), Math.abs(hi), 1e-9) : norm(ctx, v);
    h += Math.max(0, Math.min(1, t)) * 0.09;
  }
  if (ctx.hover === iso3) h += 0.025;
  if (iso3 === ctx.selected) h += 0.04;
  return h;
}

// ---- layers --------------------------------------------------------------------
// paint() runs on every hover, so it only touches colours and heights; the animated rings and
// arcs are redrawn by drawLayers() when the year, a toggle or the selection changes.
function paint(ctx) {
  const g = ctx.globe;
  if (!g) return;
  g.polygonCapColor((f) => colourFor(ctx, ctx.byIso.get(f.iso3)))
    .polygonStrokeColor((f) => (f.iso3 === ctx.selected ? "#ffffff" : "rgba(0,0,0,0.9)"))
    .polygonAltitude((f) => heightFor(ctx, f.iso3, 0.006));
  g.pointColor((c) => (c.iso3 === ctx.selected ? "#ffffff" : colourFor(ctx, c)))
    .pointAltitude((c) => heightFor(ctx, c.iso3, 0.01))
    .pointRadius((c) => (c.iso3 === ctx.selected || c.iso3 === ctx.hover ? 0.75 : 0.5));
}

function drawLayers(ctx) {
  if (!ctx.globe) return;
  ctx.globe.pointsData(ctx.points);
  drawRings(ctx);
  drawArcs(ctx);
}

function drawRings(ctx) {
  const rings = [];
  if (ctx.showConflict) {
    for (const c of ctx.data.countries) {
      const deaths = c.deaths ? c.deaths[ctx.yearIndex] : null;
      if (deaths == null || deaths < ctx.data.conflictThreshold) continue;
      const at = locate(ctx, c.iso3);
      if (at) rings.push({ iso3: c.iso3, lat: at.lat, lng: at.lng, deaths });
    }
  }
  ctx.globe.ringsData(rings)
    .ringColor(() => (t) => "rgba(253,128,120," + Math.sqrt(Math.max(0, 1 - t)).toFixed(3) + ")")
    .ringAltitude((r) => heightFor(ctx, r.iso3, 0.006) + 0.002)
    .ringMaxRadius((r) => 1.5 + Math.log10(r.deaths) * 1.4)
    .ringPropagationSpeed(1.8)
    .ringRepeatPeriod((r) => Math.max(500, 1700 - Math.log10(r.deaths) * 260));
}

function drawArcs(ctx) {
  let flows = [];
  if (ctx.showFlows) {
    const all = ctx.data.flows || [];
    flows = ctx.selected ? all.filter((f) => f.from === ctx.selected || f.to === ctx.selected).slice(0, 20)
                         : all.slice(0, ctx.data.topFlows);
  }
  const max = Math.max(1, ...flows.map((f) => f.value));
  const arcs = [];
  for (const f of flows) {
    const a = locate(ctx, f.from), b = locate(ctx, f.to);
    if (a && b) arcs.push({ ...f, startLat: a.lat, startLng: a.lng, endLat: b.lat, endLng: b.lng, w: Math.sqrt(f.value / max) });
  }
  ctx.globe.arcsData(arcs)
    .arcColor(() => ["rgba(116,177,254,0.08)", "rgba(185,215,254,0.95)"])
    .arcStroke((d) => 0.25 + 1.2 * d.w)
    .arcAltitudeAutoScale(0.35)
    .arcDashLength(0.45).arcDashGap(0.2)
    .arcDashInitialGap(() => Math.random())
    .arcDashAnimateTime(2600)
    .arcLabel((d) => '<div class="rg-tip"><b>' + esc(d.fromName) + " → " + esc(d.toName) + "</b><br>" +
      fmtPeople(d.value) + " refugees &amp; asylum seekers <span>(UNHCR " + ctx.data.flowsYear + ")</span></div>");
}

function tooltip(ctx, iso3, fallbackName) {
  const c = ctx.byIso.get(iso3);
  const name = esc(c ? c.name : fallbackName);
  const v = c ? valueOf(ctx, c) : null;
  const note = c && c.note ? "<br>" + esc(c.note) : "";
  if (ctx.data.custom) {
    const shown = v == null ? "<span>" + esc(ctx.data.emptyLabel) + "</span>" : esc(ctx.data.metricLabel) + ": " + fmtValue(ctx, v);
    return '<div class="rg-tip"><b>' + name + "</b><br>" + shown + note + "<br><span>Click for the index</span></div>";
  }
  if (v == null) return '<div class="rg-tip"><b>' + name + "</b><br><span>No score</span>" + note + "</div>";
  const tier = tierFor(ctx, c.composite[ctx.yearIndex]);
  return '<div class="rg-tip"><b>' + name + "</b> <span>" + ctx.data.years[ctx.yearIndex] + "</span><br>" +
    esc(ctx.data.metricLabel) + ": " + v.toFixed(0) + "/100" + (tier ? " · " + esc(tier.label) : "") + note +
    "<br><span>Click for the index</span></div>";
}

function renderLegend(root, ctx) {
  const data = ctx.data;
  const stops = data.colorscale.map(([t, c]) => c + " " + Math.round(t * 100) + "%").join(", ");
  root.querySelector(".rg-legend-bar").style.background = "linear-gradient(90deg, " + stops + ")";
  root.querySelector(".rg-legend-title").textContent =
    data.custom ? data.metricLabel : data.metricLabel + " risk · " + data.years[ctx.yearIndex];
  root.querySelector(".rg-legend-ticks").innerHTML = data.ticks.map((t) => "<span>" + esc(t) + "</span>").join("");
  root.querySelector(".rg-legend-keys").innerHTML =
    (ctx.showConflict ? '<div><i style="background:#fd8078"></i>Armed conflict (≥ ' + data.conflictThreshold + " battle deaths)</div>" : "") +
    (ctx.showFlows ? '<div><i style="background:#b9d7fe"></i>Refugee flows, origin → host (' + data.flowsYear + ")</div>" : "");
}

function sparkline(ctx, c) {
  const pts = c.composite.map((v, i) => [i, v]).filter(([, v]) => v != null);
  if (pts.length < 2) return "";
  const n = ctx.data.years.length - 1, W = 268, H = 54, pad = 4;
  const x = (i) => pad + (i / n) * (W - 2 * pad);
  const y = (v) => H - pad - (v / 100) * (H - 2 * pad);
  const line = pts.map(([i, v]) => x(i).toFixed(1) + "," + y(v).toFixed(1)).join(" ");
  const cur = c.composite[ctx.yearIndex];
  const dot = cur == null ? "" : '<circle cx="' + x(ctx.yearIndex).toFixed(1) + '" cy="' + y(cur).toFixed(1) +
    '" r="3.5" fill="' + (tierFor(ctx, cur) || { color: "#fff" }).color + '" stroke="#000" stroke-width="1.5"/>';
  return '<div class="rg-section">Composite since ' + ctx.data.years[0] + '</div><div class="rg-spark">' +
    '<svg viewBox="0 0 ' + W + " " + H + '" preserveAspectRatio="none">' +
    '<line x1="0" x2="' + W + '" y1="' + y(50) + '" y2="' + y(50) + '" stroke="#2c2c2a" stroke-dasharray="3 3"/>' +
    '<polyline points="' + line + '" fill="none" stroke="#c3c2b7" stroke-width="1.6" vector-effect="non-scaling-stroke"/>' +
    dot + "</svg></div>";
}

function customLine(ctx, c) {
  let html = "";
  if (ctx.data.custom) {
    const v = valueOf(ctx, c);
    html += '<div class="rg-custom">' + esc(ctx.data.metricLabel) + ": <b>" +
      (v == null ? esc(ctx.data.emptyLabel) : fmtValue(ctx, v)) + "</b></div>";
  }
  if (c.note) html += '<div class="rg-note">' + esc(c.note) + "</div>";
  return html;
}

function renderPanel(root, ctx) {
  const panel = root.querySelector(".rg-panel");
  const iso = ctx.selected;
  if (!iso) { panel.hidden = true; panel.innerHTML = ""; return; }
  const c = ctx.byIso.get(iso);
  const feature = ctx.featureByIso.get(iso);
  const yi = ctx.yearIndex, year = ctx.data.years[yi];
  const flag = c && c.flag ? '<img src="' + esc(c.flag) + '" alt="">' : "";
  let html = '<button class="rg-close" aria-label="Close">×</button><div class="rg-name">' + flag + "<span>" +
    esc(c ? c.name : feature ? feature.properties.ADMIN : iso) + "</span></div>";
  const score = c ? c.composite[yi] : null;
  if (score == null) {
    html += '<div class="rg-sub">' + esc(c ? c.region : "") + '</div><p class="rg-note">Not enough data to score this country in ' +
      year + ".</p>" + (c ? customLine(ctx, c) : "");
  } else {
    const tier = tierFor(ctx, score);
    const prev = yi > 0 ? c.composite[yi - 1] : null;
    const d = prev == null ? null : score - prev;
    const delta = d == null ? "" : '<span class="rg-delta" style="color:' + (d >= 1 ? "#fd8078" : d <= -1 ? "#5ac698" : "#898781") +
      '">' + (d >= 1 ? "▲" : d <= -1 ? "▼" : "■") + " " + (d > 0 ? "+" : "") + d.toFixed(0) + " vs " + (year - 1) + "</span>";
    html += '<div class="rg-sub">' + esc(c.region) + " · " + year + "</div>" +
      '<div class="rg-score"><span class="rg-big">' + score.toFixed(0) + '</span><span class="rg-of">/100</span>' +
      '<span class="rg-badge" style="background:' + tier.color + ";color:" + tier.text + '">' + esc(tier.label) + "</span></div>" +
      '<div class="rg-rank">Rank <b>' + c.rank[yi] + "</b> of " + ctx.data.nRanked[yi] + " " + delta + "</div>" +
      customLine(ctx, c) +
      sparkline(ctx, c) +
      '<div class="rg-section">Pillars · ' + ctx.data.years[ctx.data.years.length - 1] + "</div>" +
      '<div class="rg-pillars">' + ctx.data.pillars.map((p) => {
        const v = c.pillars[p.key];
        return '<div class="rg-prow' + (ctx.data.metric === p.key ? " rg-active" : "") + '"><span class="rg-plabel">' +
          esc(p.short) + '</span><span class="rg-ptrack"><span class="rg-pbar" style="width:' + (v == null ? 0 : v) +
          "%;background:" + p.color + '"></span></span><span class="rg-pval">' + (v == null ? "—" : v.toFixed(0)) + "</span></div>";
      }).join("") + "</div>" +
      (c.flags ? '<div class="rg-flags">⚑ ' + c.flags + " red flag" + (c.flags > 1 ? "s" : "") + " today</div>"
               : '<div class="rg-flags ok">✓ No red flags today</div>');
  }
  if (c && iso !== ctx.data.focus) html += '<button class="rg-open">Open full profile →</button>';
  panel.innerHTML = html;
  panel.hidden = false;
  panel.querySelector(".rg-close").onclick = () => select(root, ctx, null, false);
  const open = panel.querySelector(".rg-open");
  if (open) open.onclick = () => ctx.trigger("open", iso);
}

function renderTime(root, ctx) {
  const input = root.querySelector(".rg-year-input");
  input.max = String(ctx.data.years.length - 1);
  input.value = String(ctx.yearIndex);
  root.querySelector(".rg-year").textContent = ctx.data.years[ctx.yearIndex];
  root.querySelector(".rg-play").textContent = ctx.timer ? "❚❚" : "▶";
}

function setYear(root, ctx, index) {
  ctx.yearIndex = index;
  renderTime(root, ctx);
  renderLegend(root, ctx);
  paint(ctx);
  drawLayers(ctx);
  renderPanel(root, ctx);
}

function togglePlay(root, ctx) {
  if (ctx.timer) { clearInterval(ctx.timer); ctx.timer = null; renderTime(root, ctx); return; }
  if (isLatest(ctx)) setYear(root, ctx, 0);
  ctx.timer = setInterval(() => {
    if (isLatest(ctx)) { clearInterval(ctx.timer); ctx.timer = null; renderTime(root, ctx); return; }
    setYear(root, ctx, ctx.yearIndex + 1);
  }, 900);
  renderTime(root, ctx);
}

function stopSpin(root, ctx) {
  if (!ctx.spin) return;
  ctx.spin = false;
  ctx.globe.controls().autoRotate = false;
  syncButtons(root, ctx);
}

function select(root, ctx, iso, fly) {
  const changed = ctx.selected !== iso;
  ctx.selected = iso;
  if (changed) ctx.setState("selected", iso);  // Python shows this country's news
  paint(ctx);
  drawLayers(ctx);  // arcs follow the selected country
  renderPanel(root, ctx);
  if (!iso) return;
  stopSpin(root, ctx);
  const at = fly && locate(ctx, iso);
  if (at) {
    const view = ctx.globe.pointOfView();
    ctx.globe.pointOfView({ lat: at.lat, lng: at.lng, altitude: Math.min(view.altitude, 1.7) }, 900);
  }
}

function syncButtons(root, ctx) {
  root.querySelector('[data-act="spin"]').classList.toggle("on", ctx.spin);
  root.querySelector('[data-act="extrude"]').classList.toggle("on", ctx.extrude);
  root.querySelector('[data-act="flows"]').classList.toggle("on", ctx.showFlows);
  root.querySelector('[data-act="conflict"]').classList.toggle("on", ctx.showConflict);
}

function control(root, ctx, action) {
  const g = ctx.globe;
  const view = g.pointOfView();
  if (action === "in") g.pointOfView({ ...view, altitude: Math.max(0.2, view.altitude * 0.65) }, 450);
  if (action === "out") g.pointOfView({ ...view, altitude: Math.min(5.5, view.altitude / 0.65) }, 450);
  if (action === "reset") { select(root, ctx, ctx.data.focus || null, false); g.pointOfView(startView(ctx), 900); }
  if (action === "spin") { ctx.spin = !ctx.spin; g.controls().autoRotate = ctx.spin; }
  if (action === "extrude") ctx.extrude = !ctx.extrude;
  if (action === "flows") ctx.showFlows = !ctx.showFlows;
  if (action === "conflict") ctx.showConflict = !ctx.showConflict;
  if (["extrude", "flows", "conflict"].includes(action)) { paint(ctx); drawLayers(ctx); renderLegend(root, ctx); }
  syncButtons(root, ctx);
}

function fitSize(root, ctx) {
  ctx.globe.width(root.clientWidth).height(root.clientHeight);
}

function build(root, ctx, Globe, features) {
  const el = root.querySelector(".rg-canvas");
  const lastView = lastViews[ctx.data.key];
  let g;
  try { g = new Globe(el, { animateIn: !lastView }); } catch (err) { g = Globe({ animateIn: !lastView })(el); }
  ctx.globe = g;
  ctx.features = features;
  ctx.featureByIso = new Map(features.map((f) => [f.iso3, f]));
  // States too small for the 1:110m outlines (Singapore, Bahrain, most islands) are drawn as dots
  ctx.points = ctx.data.countries.filter((c) => !ctx.featureByIso.has(c.iso3) && c.lat != null && c.lng != null);
  g.backgroundColor("rgba(0,0,0,0)")
    .showAtmosphere(true).atmosphereColor("#3987e5").atmosphereAltitude(0.17)
    .showGraticules(true)
    .polygonsData(features)
    .polygonSideColor(() => "rgba(255,255,255,0.06)")
    .polygonsTransitionDuration(350)
    .polygonLabel((f) => tooltip(ctx, f.iso3, f.properties.ADMIN))
    .onPolygonHover((f) => { ctx.hover = f ? f.iso3 : null; el.style.cursor = f ? "pointer" : "grab"; paint(ctx); })
    .onPolygonClick((f) => select(root, ctx, f.iso3, true))
    .pointLat("lat").pointLng("lng").pointsMerge(false).pointsTransitionDuration(350)
    .pointLabel((c) => tooltip(ctx, c.iso3, c.name))
    .onPointHover((c) => { ctx.hover = c ? c.iso3 : null; el.style.cursor = c ? "pointer" : "grab"; paint(ctx); })
    .onPointClick((c) => select(root, ctx, c.iso3, true))
    .onGlobeClick(() => select(root, ctx, null, false));
  const material = g.globeMaterial();
  material.color.set("#0a1a33");
  if (material.emissive) material.emissive.set("#04101f");
  material.shininess = 6;
  const controls = g.controls();
  controls.autoRotate = ctx.spin;
  controls.autoRotateSpeed = 0.35;
  controls.minDistance = 115;
  controls.maxDistance = 650;
  controls.zoomSpeed = 0.9;
  controls.addEventListener("start", () => stopSpin(root, ctx));
  g.pointOfView(lastView || startView(ctx), 0);
  ctx.centreKey = JSON.stringify([ctx.data.centre, ctx.data.focus]);
  fitSize(root, ctx);
  ctx.resize = new ResizeObserver(() => fitSize(root, ctx));
  ctx.resize.observe(root);
  root.querySelectorAll(".rg-controls button").forEach((b) => { b.onclick = () => control(root, ctx, b.dataset.act); });
  root.querySelector(".rg-play").onclick = () => togglePlay(root, ctx);
  root.querySelector(".rg-year-input").oninput = (e) => {
    if (ctx.timer) togglePlay(root, ctx);
    setYear(root, ctx, Number(e.target.value));
  };
  syncButtons(root, ctx);
  setYear(root, ctx, ctx.yearIndex);
}

export default function (component) {
  const { data, parentElement, setTriggerValue, setStateValue } = component;
  const root = parentElement.querySelector(".rg-wrap");
  if (!root) return;
  const picked = data.selected || data.focus || null;
  const ctx = root.__riskGlobe || (root.__riskGlobe = {
    selected: picked, hover: null, spin: data.layers.spin && !picked, extrude: data.layers.extrude,
    showFlows: data.layers.flows, showConflict: data.layers.conflict, globe: null, timer: null,
    yearIndex: data.years.length - 1,
  });
  const newYears = !ctx.data || ctx.data.years.join() !== data.years.join() || !data.showTime;
  ctx.data = data;
  ctx.trigger = setTriggerValue;
  ctx.setState = setStateValue;
  ctx.byIso = new Map(data.countries.map((c) => [c.iso3, c]));
  if (newYears) ctx.yearIndex = data.years.length - 1;
  root.style.height = data.height + "px";
  root.style.setProperty("--rg-mobile-h", Math.min(520, data.height) + "px");
  root.querySelector(".rg-time").hidden = !data.showTime;
  if (data.hint) root.querySelector(".rg-hint").textContent = data.hint;

  if (ctx.globe) {
    ctx.points = data.countries.filter((c) => !ctx.featureByIso.has(c.iso3) && c.lat != null && c.lng != null);
    setYear(root, ctx, ctx.yearIndex);
    const key = JSON.stringify([data.centre, data.focus]);
    if (key !== ctx.centreKey) { ctx.centreKey = key; ctx.globe.pointOfView(startView(ctx), 1200); }
  } else if (!ctx.loading) {
    const status = root.querySelector(".rg-status");
    status.hidden = false;
    ctx.loading = Promise.all([loadLibrary(), loadCountries()])
      .then(([Globe, features]) => {
        build(root, ctx, Globe, features);
        status.hidden = true;
        if (ctx.selected) {  // re-mounted with a country already picked: fly back to it
          const at = locate(ctx, ctx.selected);
          if (at) ctx.globe.pointOfView({ lat: at.lat, lng: at.lng, altitude: 1.7 }, 0);
        }
      })
      .catch((err) => {
        ctx.loading = null;
        status.textContent = "The 3D globe could not load (" + err.message + "). Switch to the flat map above.";
      });
  }
  return () => {
    // Streamlit may call this on a re-render too: only tear down once the globe has left the page
    setTimeout(() => {
      if (!root.isConnected && ctx.globe) {
        lastViews[ctx.data.key] = ctx.globe.pointOfView();
        if (ctx.timer) clearInterval(ctx.timer);
        if (ctx.resize) ctx.resize.disconnect();
        if (ctx.globe._destructor) ctx.globe._destructor();
        ctx.globe = null;
      }
    }, 0);
  };
}
""".replace("__GLOBE_JS__", GLOBE_JS_URL).replace("__COUNTRIES__", COUNTRIES_URL)

_component = st.components.v2.component("risk_globe", html=_HTML, css=_CSS, js=_JS, isolate_styles=False)


def _num(value, digits: int = 1) -> float | None:
    return None if value is None or pd.isna(value) else round(float(value), digits)


def _by_year(hist: pd.DataFrame, column: str, years: list[int], digits: int = 0) -> dict[str, list]:
    wide = hist.pivot_table(index="iso3", columns="year", values=column, aggfunc="first").reindex(columns=years)
    return {iso3: [_num(v, digits) for v in row] for iso3, row in zip(wide.index, wide.to_numpy())}


def _flows(flows: pd.DataFrame | None, names: dict[str, str], focus: str | None) -> tuple[list[dict], int | None]:
    """Largest origin -> host flows (top 300 overall, plus the focus country's own top 30).

    The globe draws the top 40, or only the flows of the selected country.
    """
    if flows is None or flows.empty:
        return [], None
    known = flows[flows["origin"].isin(names) & flows["host"].isin(names)]
    top = known.nlargest(300, "value")
    if focus:
        own = known[(known["origin"] == focus) | (known["host"] == focus)].nlargest(30, "value")
        top = pd.concat([top, own]).drop_duplicates(["origin", "host"]).sort_values("value", ascending=False)
    return [
        {"from": r.origin, "to": r.host, "value": float(r.value), "fromName": names[r.origin], "toName": names[r.host]}
        for r in top.itertuples(index=False)
    ], int(flows["year"].max())


DEFAULT_LAYERS = {"spin": True, "extrude": True, "flows": True, "conflict": True}


def risk_globe(table: pd.DataFrame, hist: pd.DataFrame, flows: pd.DataFrame | None, metric: str, metric_label: str,
               in_view: set[str] | None = None, region: str | None = None, selected: str | None = None,
               key: str = "risk_globe", *, custom: dict | pd.Series | None = None, colorscale: list | None = None,
               value_range: tuple[float, float] = (0, 100), value_format: str = "score",
               ticks: list[str] | None = None, notes: dict | None = None, empty_label: str = "No data",
               extrude_abs: bool = False, layers: dict | None = None, height: int = HEIGHT, focus: str | None = None,
               hint: str | None = None) -> tuple[str | None, str | None]:
    """Draw the globe.

    By default countries are coloured by `metric` (composite or a pillar key) with the year slider. Pass `custom`
    ({iso3: value}) to colour by anything else instead — with its own `colorscale`, `value_range` and
    `value_format` ("score", "signed", "days" or plain); `notes` adds a line per country to the tooltip and panel.
    Countries outside `in_view` are dimmed; `region` or `focus` (a country) turns the camera; `layers` sets which
    of spin / extrude / flows / conflict start switched on.
    Returns (country to open, selected country): the first is set only when "Open full profile" is clicked.
    """
    years = sorted(int(y) for y in hist["year"].unique())
    composite = _by_year(hist, "composite", years)
    rank = _by_year(hist, "rank", years)
    deaths = _by_year(hist, "battle_deaths_raw", years)
    value = None if metric == "composite" or custom is not None else _by_year(hist, metric, years)
    custom = dict(custom) if custom is not None else None
    notes = notes or {}
    in_view = set(table["iso3"]) if in_view is None else in_view
    n_ranked = hist.groupby("year")["composite"].count().reindex(years).fillna(0).astype(int).tolist()
    blank = [None] * len(years)
    countries = []
    for r in table.to_dict("records"):
        iso3 = r["iso3"]
        entry = {
            "iso3": iso3,
            "name": r["name"],
            "region": r["region"],
            "flag": r.get("flag") if isinstance(r.get("flag"), str) else None,
            "lat": _num(r.get("lat"), 3),
            "lng": _num(r.get("lng"), 3),
            "composite": composite.get(iso3, blank),
            "rank": rank.get(iso3, blank),
            "deaths": deaths.get(iso3, blank),
            "pillars": {p.key: _num(r.get(p.key)) for p in config.PILLARS},
            "flags": int(r.get("flags") or 0),
            "inView": iso3 in in_view,
        }
        if value is not None:
            entry["value"] = value.get(iso3, blank)
        if custom is not None:
            entry["custom"] = _num(custom.get(iso3), 2)
        if notes.get(iso3):
            entry["note"] = str(notes[iso3])
        countries.append(entry)
    flow_list, flows_year = _flows(flows, dict(zip(table["iso3"], table["name"])), focus)
    centre = config.REGION_CENTERS.get(region or "")
    data = {
        "key": key,
        "height": height,
        "years": years,
        "showTime": custom is None,
        "nRanked": n_ranked,
        "metric": metric,
        "metricLabel": metric_label,
        "custom": custom is not None,
        "range": list(value_range),
        "valueFormat": value_format,
        "emptyLabel": empty_label,
        "extrudeAbs": extrude_abs,
        "ticks": ticks or ["0 · lower", "50", "higher · 100"],
        "colorscale": colorscale or config.map_colorscale(metric),
        "noData": config.NO_DATA_COLOR,
        "outOfView": OUT_OF_VIEW_COLOR,
        "centre": list(centre) if centre else None,
        "focus": focus,
        "hint": hint,
        "layers": {**DEFAULT_LAYERS, **(layers or {})},
        "selected": selected,
        "pillars": [{"key": p.key, "short": p.short, "color": config.PILLAR_COLORS[p.key]} for p in config.PILLARS],
        "tierList": [{"label": t.label, "lower": t.lower, "color": t.color, "text": t.text_on} for t in config.TIERS],
        "conflictThreshold": CONFLICT_THRESHOLD,
        "flows": flow_list,
        "flowsYear": flows_year,
        "topFlows": TOP_FLOWS,
        "countries": countries,
    }
    result = _component(key=key, data=data, default={"selected": selected},
                        on_open_change=lambda: None, on_selected_change=lambda: None)
    return getattr(result, "open", None), getattr(result, "selected", None)
