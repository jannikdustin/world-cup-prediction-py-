#!/usr/bin/env python3
"""generate_combined_dashboard.py — Baut EIN Dashboard mit Tabs aus allen drei
Ergebnis-Dateien (WM, Top-5-Ligen + Europa, Tennis ATP), inkl. Bankroll-
Kennzahlen und Charts pro Tab (Instrumenten-Panel-Optik, siehe HTML_TEMPLATE).

Liest results.json, results_clubs.json, results_tennis.json und die
zugehoerigen ledger_*.json (alle optional -- fehlt eine Datei, wird der
jeweilige Tab/Wert einfach leer/0 angezeigt statt das Skript abbrechen zu
lassen) und rendert combined_dashboard.html.

Start:
    python generate_combined_dashboard.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "combined_dashboard.html")

SOURCES = [
    ("wm", "WM 2026", os.path.join(HERE, "results.json"), os.path.join(HERE, "ledger_wm.json")),
    ("clubs", "Top 5 Ligen + Europa", os.path.join(HERE, "results_clubs.json"), os.path.join(HERE, "ledger_clubs.json")),
    ("tennis", "Tennis ATP", os.path.join(HERE, "results_tennis.json"), os.path.join(HERE, "ledger_tennis.json")),
]


def load_or_empty(path):
    if not os.path.exists(path):
        return {"generated_at": None, "match_count": 0, "value_count": 0, "skipped": [], "matches": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_ledger_or_empty(path):
    if not os.path.exists(path):
        return {"starting_bankroll": 1000.0, "current_bankroll": 1000.0, "bets": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    data_by_tab = {}
    for tab_id, label, results_path, ledger_path in SOURCES:
        results = load_or_empty(results_path)
        ledger = load_ledger_or_empty(ledger_path)
        data_by_tab[tab_id] = {"label": label, **results, "bankroll": ledger}

    data_json = json.dumps(data_by_tab, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Kombiniertes Dashboard erzeugt -> {OUT_PATH}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Value Radar</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.4/chart.umd.min.js"></script>
<style>
  :root{
    --void: #090c11;
    --panel: #10161f;
    --panel-raised: #161d29;
    --line: #1e2732;
    --ink: #e7ecf2;
    --ink-dim: #7d8896;
    --ink-faint: #4d5866;
    --phosphor: #46e0c4;
    --phosphor-dim: rgba(70, 224, 196, 0.13);
    --amber: #f4a637;
    --amber-dim: rgba(244, 166, 55, 0.14);
    --rose: #ef5875;
    --rose-dim: rgba(239, 88, 117, 0.13);
    --font-display: "Space Grotesk", "IBM Plex Sans", sans-serif;
    --font-body: "IBM Plex Sans", -apple-system, sans-serif;
    --font-data: "IBM Plex Mono", "SF Mono", Consolas, monospace;
  }
  *{ box-sizing: border-box; }
  html{ background: var(--void); }
  body{
    margin:0;
    background: var(--void);
    background-image: radial-gradient(ellipse 900px 420px at 15% -10%, rgba(70,224,196,0.06), transparent 60%);
    color: var(--ink);
    font-family: var(--font-body);
    padding: 0 0 72px 0;
    -webkit-font-smoothing: antialiased;
  }
  a{ color: var(--phosphor); }
  ::selection{ background: var(--phosphor-dim); color: var(--ink); }

  .wrap{ max-width: 1040px; margin: 0 auto; padding: 0 20px; }

  /* ---------- Masthead + Radar signature ---------- */
  .masthead{
    display: flex; align-items: center; gap: 20px;
    padding: 28px 0 22px;
    border-bottom: 1px solid var(--line);
  }
  .radar{ position: relative; width: 64px; height: 64px; flex: none; }
  .radar-face{
    position:absolute; inset:0; border-radius:50%;
    background:
      radial-gradient(circle at center,
        transparent 0 28%, var(--line) 28% 29.5%,
        transparent 29.5% 53%, var(--line) 53% 54.5%,
        transparent 54.5% 78%, var(--line) 78% 79.5%,
        transparent 79.5%);
    border: 1px solid var(--line);
  }
  .radar-crosshair{ position:absolute; inset:0; }
  .radar-crosshair::before, .radar-crosshair::after{
    content:""; position:absolute; background: var(--line);
  }
  .radar-crosshair::before{ left:50%; top:2px; bottom:2px; width:1px; transform:translateX(-50%); }
  .radar-crosshair::after{ top:50%; left:2px; right:2px; height:1px; transform:translateY(-50%); }
  .radar-sweep{
    position:absolute; inset:0; border-radius:50%;
    background: conic-gradient(from 0deg, rgba(70,224,196,0.65), rgba(70,224,196,0.08) 20%, transparent 38%);
    animation: radar-spin 4.5s linear infinite;
    mix-blend-mode: screen;
  }
  .radar-blip{
    position:absolute; width:5px; height:5px; margin:-2.5px 0 0 -2.5px;
    border-radius:50%; background: var(--amber);
    box-shadow: 0 0 6px 1px var(--amber);
  }
  @keyframes radar-spin{ to{ transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce){ .radar-sweep{ animation: none; } }

  .masthead-text h1{
    font-family: var(--font-display); font-weight: 700;
    font-size: 22px; letter-spacing: -0.01em; margin: 0;
  }
  .masthead-text .sub{
    font-family: var(--font-data); color: var(--ink-dim); font-size: 12px;
    margin-top: 4px; letter-spacing: .01em;
  }
  .masthead-text .sub .dot{ color: var(--phosphor); }

  /* ---------- Console tab bar ---------- */
  .tabs{
    display: flex; gap: 8px; padding: 16px 0; flex-wrap: wrap;
  }
  .tab-btn{
    display:flex; align-items:center; gap:8px;
    background: var(--panel);
    border: 1px solid var(--line);
    color: var(--ink-dim);
    font-family: var(--font-body);
    font-size: 13px; font-weight: 600;
    padding: 9px 14px; border-radius: 8px;
    cursor: pointer;
  }
  .tab-btn .dot-ind{ width:6px; height:6px; border-radius:50%; background: var(--ink-faint); flex:none; }
  .tab-btn.active{
    color: var(--ink); border-color: var(--phosphor);
    background: var(--phosphor-dim);
  }
  .tab-btn.active .dot-ind{ background: var(--phosphor); box-shadow: 0 0 5px var(--phosphor); }
  .tab-btn .count-pill{
    font-family: var(--font-data);
    background: var(--amber-dim); color: var(--amber);
    font-size: 11px; padding: 1px 6px; border-radius: 20px;
  }

  main{ padding-top: 4px; }
  .tab-panel{ display: none; }
  .tab-panel.active{ display: block; }

  /* ---------- Stat tile grid ---------- */
  .stat-grid{
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
    background: var(--line); border: 1px solid var(--line); border-radius: 10px;
    overflow: hidden; margin-bottom: 16px;
  }
  .stat-tile{ background: var(--panel); padding: 14px 14px 12px; }
  .stat-tile .label{
    font-family: var(--font-data); font-size: 10px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--ink-dim); margin-bottom: 6px;
  }
  .stat-tile .value{
    font-family: var(--font-display); font-weight: 700; font-size: 20px; line-height: 1.1;
  }
  .stat-tile .value.pos{ color: var(--phosphor); }
  .stat-tile .value.neg{ color: var(--rose); }
  .stat-tile .value.amber{ color: var(--amber); }
  .stat-tile .sub{ font-family: var(--font-data); font-size: 11px; color: var(--ink-faint); margin-top: 3px; }
  @media (max-width: 720px){ .stat-grid{ grid-template-columns: repeat(2, 1fr); } }

  /* ---------- Chart row ---------- */
  .chart-row{ display: grid; grid-template-columns: 1.6fr 1fr; gap: 12px; margin-bottom: 12px; }
  @media (max-width: 780px){ .chart-row{ grid-template-columns: 1fr; } }
  .chart-box{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px 10px;
  }
  .chart-box h3{
    font-family: var(--font-data); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--ink-dim); margin: 0 0 10px; font-weight: 500;
  }
  .chart-canvas-wrap{ position: relative; height: 160px; }
  .chart-canvas-wrap.small{ height: 140px; }
  .chart-empty{
    display:flex; align-items:center; justify-content:center; height:100%;
    color: var(--ink-faint); font-size: 12px; font-family: var(--font-data);
  }

  /* ---------- Bet log ---------- */
  .bet-log-box{
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    padding: 14px 16px 6px; margin-bottom: 20px;
  }
  .bet-log-box h3{
    font-family: var(--font-data); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--ink-dim); margin: 0 0 8px; font-weight: 500;
  }
  table.bet-log{ width: 100%; border-collapse: collapse; font-size: 12px; }
  table.bet-log th{
    text-align: left; color: var(--ink-faint); font-weight: 500; font-size: 10px;
    text-transform: uppercase; letter-spacing: .04em; padding: 5px 6px;
    border-bottom: 1px solid var(--line); font-family: var(--font-data);
  }
  table.bet-log td{
    padding: 6px 6px; border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: var(--font-data);
  }
  table.bet-log td.status-won{ color: var(--phosphor); }
  table.bet-log td.status-lost{ color: var(--rose); }
  table.bet-log td.status-void{ color: var(--ink-faint); font-style: italic; }
  table.bet-log td.match-cell{ font-family: var(--font-body); }
  .bet-log-empty{ padding: 16px 0; color: var(--ink-faint); font-size: 12px; font-family: var(--font-data); }

  /* ---------- Match list ---------- */
  .section-label{
    font-family: var(--font-data); font-size: 11px; text-transform: uppercase;
    letter-spacing: .06em; color: var(--ink-dim); margin: 22px 2px 10px;
  }
  .empty-state{
    text-align:center; padding: 48px 20px; color: var(--ink-faint);
    border: 1px dashed var(--line); border-radius: 10px; font-size: 13px;
  }
  .match-card{
    background: var(--panel); border: 1px solid var(--line);
    border-left: 3px solid var(--ink-faint);
    border-radius: 8px; padding: 16px 18px; margin-bottom: 10px;
  }
  .match-card.tier-strong{ border-left-color: var(--amber); box-shadow: 0 0 0 1px var(--amber-dim) inset; }
  .match-card.tier-value{ border-left-color: var(--phosphor); box-shadow: 0 0 0 1px var(--phosphor-dim) inset; }

  .match-top{ display:flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
  .teams{ font-family: var(--font-body); font-size: 16px; font-weight: 600; }
  .kickoff{ font-family: var(--font-data); font-size: 11px; color: var(--ink-dim); margin-top: 3px; }

  .badge{
    display:inline-flex; align-items:center; gap:5px;
    font-family: var(--font-data); font-size: 10.5px; font-weight: 600;
    padding: 3px 9px; border-radius: 20px; letter-spacing: .02em; white-space: nowrap;
  }
  .badge.tier-strong{ background: var(--amber-dim); color: var(--amber); }
  .badge.tier-value{ background: var(--phosphor-dim); color: var(--phosphor); }
  .badge.tier-none{ background: rgba(255,255,255,0.04); color: var(--ink-faint); }

  table.outcomes{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 12.5px; }
  table.outcomes th{
    text-align: left; color: var(--ink-faint); font-weight: 500; font-size: 10px;
    text-transform: uppercase; letter-spacing: .04em; padding: 4px 8px;
    border-bottom: 1px solid var(--line); font-family: var(--font-data);
  }
  table.outcomes td{
    padding: 6px 8px; border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: var(--font-data);
  }
  table.outcomes tr:last-child td{ border-bottom: none; }
  table.outcomes td.ev-pos{ color: var(--phosphor); font-weight: 600; }
  table.outcomes td.ev-neg{ color: var(--ink-faint); }
  table.outcomes td.label{ font-family: var(--font-body); }

  .skipped{ margin-top: 14px; font-size: 11.5px; color: var(--ink-faint); font-family: var(--font-data); line-height: 1.6; }

  .footer-note{
    margin-top: 30px; padding-top: 16px; border-top: 1px solid var(--line);
    font-size: 11.5px; color: var(--ink-faint); line-height: 1.7; font-family: var(--font-body);
  }
</style>
</head>
<body>

<div class="wrap">
  <div class="masthead">
    <div class="radar" id="radar">
      <div class="radar-face"></div>
      <div class="radar-crosshair"></div>
      <div class="radar-sweep"></div>
      <div id="radar-blips"></div>
    </div>
    <div class="masthead-text">
      <h1>Value Radar</h1>
      <div class="sub">Modell <span class="dot">·</span> Markt <span class="dot">·</span> Bankroll — drei Signal-Feeds, ein Panel</div>
    </div>
  </div>

  <div class="tabs" id="tabs"></div>
  <main id="main"></main>

  <div class="footer-note">
    Value = Edge des Modells gegenüber dem no-vig-Marktkonsens, kein garantierter Gewinn.
    Die Bankroll-Kurve ist simuliertes Paper Trading (voller Kelly auf Signale &gt; 3% EV,
    nur Prematch) — es wird kein echtes Geld eingesetzt. Große Abweichungen zuerst
    hinterfragen (Aufstellung, Form, Verletzungen), nicht blind übernehmen.
  </div>
</div>

<script>
const DATA = __DATA_JSON__;
const TAB_IDS = Object.keys(DATA);
const charts = {};
const HAS_CHART = typeof Chart !== "undefined";

if (HAS_CHART){
  Chart.defaults.color = "#7d8896";
  Chart.defaults.font.family = "'IBM Plex Mono', monospace";
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = "#1e2732";
}

function fmtTime(iso){
  if(!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" });
}
function fmtEUR(v){ return v.toLocaleString("de-DE", {minimumFractionDigits:2, maximumFractionDigits:2}) + " €"; }
function tierOf(evPct){
  if(evPct > 8) return "strong";
  if(evPct > 3) return "value";
  return "none";
}

/* ---------- Radar signature (data-bound blips) ---------- */
function hashAngle(str){
  let h = 0;
  for(let i=0;i<str.length;i++){ h = (h*31 + str.charCodeAt(i)) >>> 0; }
  return (h % 360);
}
function renderRadar(matches){
  const host = document.getElementById("radar-blips");
  host.innerHTML = "";
  const signals = (matches || []).filter(m => m.is_value_match).slice(0, 12);
  signals.forEach(m => {
    const angle = hashAngle(m.home + m.away) * Math.PI / 180;
    const radiusPct = Math.min(0.92, 0.28 + (m.best_ev_pct / 20));
    const cx = 50 + Math.cos(angle) * radiusPct * 50;
    const cy = 50 + Math.sin(angle) * radiusPct * 50;
    const blip = document.createElement("div");
    blip.className = "radar-blip";
    blip.style.left = cx + "%";
    blip.style.top = cy + "%";
    blip.title = `${m.home} vs ${m.away} · +${m.best_ev_pct.toFixed(1)}%`;
    host.appendChild(blip);
  });
}

/* ---------- Derived stats ---------- */
function computeStats(d){
  const bk = d.bankroll;
  const settled = bk.bets.filter(b => b.status === "won" || b.status === "lost");
  const won = bk.bets.filter(b => b.status === "won").length;
  const lost = bk.bets.filter(b => b.status === "lost").length;
  const voided = bk.bets.filter(b => b.status === "void").length;
  const pendingBets = bk.bets.filter(b => b.status === "pending")
    .sort((a, b) => new Date(a.commence_time) - new Date(b.commence_time));
  const exposure = pendingBets.reduce((sum, b) => sum + b.stake, 0);
  // current_bankroll ist der LIVE-Kontostand: Einsaetze werden beim
  // Platzieren sofort abgezogen (siehe bankroll.py), nicht erst bei
  // Abrechnung. "equity" rechnet die gerade gebundenen Einsaetze wieder
  // dazu und zeigt den Gesamtwert inkl. offener Wetten.
  const equity = bk.current_bankroll + exposure;
  const roi = ((equity - bk.starting_bankroll) / bk.starting_bankroll) * 100;
  const winRate = settled.length ? (won / settled.length) * 100 : null;

  const matches = d.matches || [];
  const avgEV = matches.length ? matches.reduce((s,m) => s + m.best_ev_pct, 0) / matches.length : null;
  const bestEV = matches.length ? Math.max(...matches.map(m => m.best_ev_pct)) : null;
  const valueRate = matches.length ? (d.value_count / matches.length) * 100 : null;

  return { settled, won, lost, voided, pendingBets, exposure, equity, roi, winRate, avgEV, bestEV, valueRate };
}

/* ---------- Stat tiles ---------- */
function statTile(label, value, sub, cls){
  return `<div class="stat-tile">
    <div class="label">${label}</div>
    <div class="value${cls ? " " + cls : ""}">${value}</div>
    ${sub ? `<div class="sub">${sub}</div>` : ""}
  </div>`;
}

function renderStatGrid(d, s){
  const bk = d.bankroll;
  const roiCls = s.roi >= 0 ? "pos" : "neg";
  const winRateStr = s.winRate === null ? "—" : s.winRate.toFixed(0) + "%";
  const avgEvStr = s.avgEV === null ? "—" : (s.avgEV >= 0 ? "+" : "") + s.avgEV.toFixed(1) + "%";
  const bestEvStr = s.bestEV === null ? "—" : "+" + s.bestEV.toFixed(1) + "%";

  const grid = document.createElement("div");
  grid.className = "stat-grid";
  grid.innerHTML = [
    statTile("Kontostand", fmtEUR(bk.current_bankroll), "frei verfügbar"),
    statTile("Gesamtwert", fmtEUR(s.equity), `Start ${fmtEUR(bk.starting_bankroll)}`),
    statTile("ROI", (s.roi >= 0 ? "+" : "") + s.roi.toFixed(1) + "%", "auf Gesamtwert", roiCls),
    statTile("Im Einsatz", fmtEUR(s.exposure), `${s.pendingBets.length} offene Position${s.pendingBets.length === 1 ? "" : "en"}`, s.exposure > 0 ? "amber" : null),
    statTile("Trefferquote", winRateStr, `${s.won}W · ${s.lost}L${s.voided ? " · " + s.voided + " storniert" : ""}`),
    statTile("Ø Edge (Scan)", avgEvStr, `${d.match_count} geprüft`),
    statTile("Bester Edge", bestEvStr, "heute", s.bestEV > 8 ? "amber" : null),
    statTile("Value-Quote", s.valueRate === null ? "—" : s.valueRate.toFixed(0) + "%", `${d.value_count} von ${d.match_count}`),
  ].join("");
  return grid;
}

/* ---------- Charts ---------- */
function renderBankrollChart(canvas, bk, s){
  const curve = [bk.starting_bankroll, ...s.settled.map(b => b.bankroll_after)];
  if(curve.length < 2){
    canvas.parentElement.innerHTML = '<div class="chart-empty">Noch keine abgerechneten Wetten für eine Kurve.</div>';
    return;
  }
  const rising = curve[curve.length-1] >= curve[0];
  const lineColor = rising ? "#46e0c4" : "#ef5875";
  const fillColor = rising ? "rgba(70,224,196,0.10)" : "rgba(239,88,117,0.10)";
  new Chart(canvas, {
    type: "line",
    data: {
      labels: curve.map((_, i) => i === 0 ? "Start" : "#" + i),
      datasets: [{
        data: curve, borderColor: lineColor, backgroundColor: fillColor,
        fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: "#1e2732" }, ticks: { maxTicksLimit: 6 } },
        y: { grid: { color: "#1e2732" }, ticks: { callback: v => v.toFixed(0) + "€" } },
      }
    }
  });
}

function renderWinLossChart(canvas, s){
  if(s.settled.length === 0 && s.voided === 0){
    canvas.parentElement.innerHTML = '<div class="chart-empty">Noch keine Bilanz.</div>';
    return;
  }
  new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: ["Gewonnen", "Verloren", "Storniert"],
      datasets: [{
        data: [s.won, s.lost, s.voided],
        backgroundColor: ["#46e0c4", "#ef5875", "#2a3441"],
        borderColor: "#10161f", borderWidth: 2,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: "68%",
      plugins: { legend: { position: "bottom", labels: { boxWidth: 8, padding: 10 } } }
    }
  });
}

function renderEvDistChart(canvas, matches){
  if(!matches || matches.length === 0){
    canvas.parentElement.innerHTML = '<div class="chart-empty">Keine Spiele im aktuellen Scan.</div>';
    return;
  }
  const buckets = [
    { label: "< 0%", test: v => v < 0 },
    { label: "0–3%", test: v => v >= 0 && v < 3 },
    { label: "3–6%", test: v => v >= 3 && v < 6 },
    { label: "6–10%", test: v => v >= 6 && v < 10 },
    { label: "> 10%", test: v => v >= 10 },
  ];
  const counts = buckets.map(b => matches.filter(m => b.test(m.best_ev_pct)).length);
  new Chart(canvas, {
    type: "bar",
    data: {
      labels: buckets.map(b => b.label),
      datasets: [{
        data: counts,
        backgroundColor: ["#2a3441", "#2a3441", "#1f5c52", "#2c8a78", "#f4a637"],
        borderRadius: 3, maxBarThickness: 28,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: "#1e2732" }, ticks: { precision: 0 } },
      }
    }
  });
}

function initTabCharts(tabId, d, s){
  if(charts[tabId]) return;
  charts[tabId] = true;

  const bkCanvas = document.getElementById("chart-bankroll-" + tabId);
  const wlCanvas = document.getElementById("chart-winloss-" + tabId);
  const evCanvas = document.getElementById("chart-evdist-" + tabId);

  if(!HAS_CHART){
    // Chart.js-CDN nicht geladen (langsames Netz, Content-Blocker o.ae.) --
    // klare Meldung statt stillschweigend leerer Boxen.
    const msg = '<div class="chart-empty">Diagramm-Bibliothek konnte nicht geladen werden (CDN nicht erreichbar).</div>';
    [bkCanvas, wlCanvas, evCanvas].forEach(c => { if(c) c.parentElement.innerHTML = msg; });
    return;
  }

  if(bkCanvas) renderBankrollChart(bkCanvas, d.bankroll, s);
  if(wlCanvas) renderWinLossChart(wlCanvas, s);
  if(evCanvas) renderEvDistChart(evCanvas, d.matches);
}

/* ---------- Match cards ---------- */
function renderMatch(m){
  const tier = tierOf(m.best_ev_pct);
  const card = document.createElement("div");
  card.className = "match-card" + (tier !== "none" ? " tier-" + tier : "");

  const rows = m.outcomes.map(o => {
    const evClass = o.ev_pct > 0 ? "ev-pos" : "ev-neg";
    return `<tr>
      <td class="label">${o.label}</td>
      <td>${o.model_prob_pct.toFixed(1)}%</td>
      <td>${o.odd.toFixed(2)}</td>
      <td>${o.novig_prob_pct.toFixed(1)}%</td>
      <td>${o.fair_odd !== null ? o.fair_odd.toFixed(2) : "—"}</td>
      <td class="${evClass}">${o.ev_pct > 0 ? "+" : ""}${o.ev_pct.toFixed(1)}%</td>
      <td>${o.kelly_pct.toFixed(1)}%</td>
    </tr>`;
  }).join("");

  const badgeLabel = tier === "none" ? "kein Edge" : (tier === "strong" ? "STARK · " : "VALUE · ") + m.best_outcome;

  card.innerHTML = `
    <div class="match-top">
      <div>
        <div class="teams">${m.home} vs ${m.away}</div>
        <div class="kickoff">Anstoss ${fmtTime(m.commence_time)}${m.league ? " · " + m.league : ""} · ${m.bookmaker_count} Buchmacher · Marge ${m.bookmaker_margin_pct.toFixed(1)}%</div>
      </div>
      <span class="badge tier-${tier}">${badgeLabel}</span>
    </div>
    <table class="outcomes">
      <thead>
        <tr><th>Ausgang</th><th>Modell</th><th>Quote</th><th>Markt (no-vig)</th><th>Faire Quote</th><th>EV</th><th>Kelly</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  return card;
}

/* ---------- Offene Positionen ---------- */
function renderOpenPositions(s){
  if(s.pendingBets.length === 0){
    return '<div class="bet-log-empty">Gerade keine offenen Positionen — die gesamte Bankroll ist frei.</div>';
  }
  const rows = s.pendingBets.map(b => `
    <tr>
      <td class="match-cell">${b.home} vs ${b.away}</td>
      <td>${b.outcome}</td>
      <td>${b.odd.toFixed(2)}</td>
      <td>${fmtEUR(b.stake)}</td>
      <td>${fmtTime(b.commence_time)}</td>
    </tr>`).join("");
  return `<table class="bet-log"><thead><tr>
      <th>Match</th><th>Tipp</th><th>Quote</th><th>Einsatz</th><th>Anstoß</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

/* ---------- Bet log ---------- */
function renderBetLog(s){
  if(s.settled.length === 0){
    return '<div class="bet-log-empty">Noch keine abgerechneten Wetten.</div>';
  }
  const rows = s.settled.slice(-10).reverse().map(b => `
    <tr>
      <td class="match-cell">${b.home} vs ${b.away}</td>
      <td>${b.outcome}</td>
      <td>${fmtEUR(b.stake)}</td>
      <td>${b.odd.toFixed(2)}</td>
      <td class="status-${b.status}">${b.status === "won" ? "Gewonnen" : "Verloren"}</td>
      <td>${fmtEUR(b.bankroll_after)}</td>
    </tr>`).join("");
  return `<table class="bet-log"><thead><tr>
      <th>Match</th><th>Tipp</th><th>Einsatz</th><th>Quote</th><th>Ergebnis</th><th>Bankroll danach</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
}

/* ---------- Tab panel assembly ---------- */
function renderTabPanel(tabId){
  const d = DATA[tabId];
  const s = computeStats(d);
  const panel = document.createElement("div");
  panel.className = "tab-panel";
  panel.id = "panel-" + tabId;
  panel.dataset.ready = "0";

  panel.appendChild(renderStatGrid(d, s));

  const chartRow = document.createElement("div");
  chartRow.className = "chart-row";
  chartRow.innerHTML = `
    <div class="chart-box">
      <h3>Bankroll-Verlauf</h3>
      <div class="chart-canvas-wrap"><canvas id="chart-bankroll-${tabId}"></canvas></div>
    </div>
    <div class="chart-box">
      <h3>Bilanz</h3>
      <div class="chart-canvas-wrap small"><canvas id="chart-winloss-${tabId}"></canvas></div>
    </div>
  `;
  panel.appendChild(chartRow);

  const evBox = document.createElement("div");
  evBox.className = "chart-box";
  evBox.style.marginBottom = "20px";
  evBox.innerHTML = `<h3>Edge-Verteilung heutiger Scan</h3>
    <div class="chart-canvas-wrap small"><canvas id="chart-evdist-${tabId}"></canvas></div>`;
  panel.appendChild(evBox);

  const openPosBox = document.createElement("div");
  openPosBox.className = "bet-log-box";
  openPosBox.innerHTML = `<h3>Offene Positionen — jetzt gebundenes Geld</h3>${renderOpenPositions(s)}`;
  panel.appendChild(openPosBox);

  const betLogBox = document.createElement("div");
  betLogBox.className = "bet-log-box";
  betLogBox.innerHTML = `<h3>Letzte abgerechnete Wetten</h3>${renderBetLog(s)}`;
  panel.appendChild(betLogBox);

  const sectionLabel = document.createElement("div");
  sectionLabel.className = "section-label";
  sectionLabel.textContent = `Spiele im aktuellen Scan · Stand ${fmtTime(d.generated_at)}`;
  panel.appendChild(sectionLabel);

  if(!d.matches || d.matches.length === 0){
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Keine Spiele mit vollständigem Quotenmarkt gefunden.";
    panel.appendChild(empty);
  } else {
    d.matches.forEach(m => panel.appendChild(renderMatch(m)));
  }

  if(d.skipped && d.skipped.length){
    const skip = document.createElement("div");
    skip.className = "skipped";
    skip.textContent = "Übersprungen: " + d.skipped.join(" · ");
    panel.appendChild(skip);
  }

  return panel;
}

function switchTab(tabId){
  TAB_IDS.forEach(id => {
    document.getElementById("panel-" + id).classList.toggle("active", id === tabId);
    document.getElementById("tabbtn-" + id).classList.toggle("active", id === tabId);
  });
  window.location.hash = tabId;
  renderRadar(DATA[tabId].matches);
  initTabCharts(tabId, DATA[tabId], computeStats(DATA[tabId]));
}

function init(){
  const tabsEl = document.getElementById("tabs");
  const mainEl = document.getElementById("main");

  TAB_IDS.forEach(tabId => {
    const d = DATA[tabId];
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.id = "tabbtn-" + tabId;
    btn.innerHTML = `<span class="dot-ind"></span>${d.label}${d.value_count > 0 ? `<span class="count-pill">${d.value_count}</span>` : ""}`;
    btn.onclick = () => switchTab(tabId);
    tabsEl.appendChild(btn);

    mainEl.appendChild(renderTabPanel(tabId));
  });

  const hashTab = window.location.hash.replace("#", "");
  const initialTab = TAB_IDS.includes(hashTab) ? hashTab : TAB_IDS[0];
  switchTab(initialTab);
}

init();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
