#!/usr/bin/env python3
"""generate_combined_dashboard.py — Baut EIN Dashboard mit Tabs aus allen drei
Ergebnis-Dateien (WM, Top-5-Ligen + Europa, Tennis ATP), statt drei separater
Seiten mit einer Verteiler-Startseite.

Liest results.json, results_clubs.json, results_tennis.json (alle optional --
fehlt eine Datei, wird der jeweilige Tab einfach leer angezeigt statt das
Skript abbrechen zu lassen) und rendert combined_dashboard.html.

Start:
    python generate_combined_dashboard.py
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PATH = os.path.join(HERE, "combined_dashboard.html")

SOURCES = [
    ("wm", "⚽ WM 2026", os.path.join(HERE, "results.json"), os.path.join(HERE, "ledger_wm.json")),
    ("clubs", "🏆 Top 5 Ligen + Europa", os.path.join(HERE, "results_clubs.json"), os.path.join(HERE, "ledger_clubs.json")),
    ("tennis", "🎾 Tennis ATP", os.path.join(HERE, "results_tennis.json"), os.path.join(HERE, "ledger_tennis.json")),
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
<style>
  :root{
    --bg: #0b0d0f;
    --panel: #14171a;
    --panel-border: #23272b;
    --text: #e7e9ea;
    --text-dim: #8b9196;
    --value: #3ddc84;
    --value-glow: rgba(61, 220, 132, 0.15);
    --neutral: #4a5157;
    --warn: #d98c3c;
  }
  *{ box-sizing: border-box; }
  body{
    margin:0;
    background: var(--bg);
    color: var(--text);
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    padding: 0 0 64px 0;
  }

  header{
    padding: 32px 24px 0;
    max-width: 980px;
    margin: 0 auto;
  }
  header h1{
    font-size: 26px;
    margin: 0 0 4px 0;
    letter-spacing: -0.02em;
  }
  header .sub{
    color: var(--text-dim);
    font-size: 13px;
    margin-bottom: 20px;
  }

  .tabs{
    display: flex;
    gap: 4px;
    max-width: 980px;
    margin: 0 auto;
    padding: 0 24px;
    border-bottom: 1px solid var(--panel-border);
  }
  .tab-btn{
    background: none;
    border: none;
    color: var(--text-dim);
    font-size: 15px;
    font-weight: 600;
    padding: 12px 18px;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    font-family: inherit;
  }
  .tab-btn.active{
    color: var(--text);
    border-bottom-color: var(--value);
  }
  .tab-btn .count-pill{
    display: inline-block;
    margin-left: 6px;
    background: var(--value-glow);
    color: var(--value);
    font-size: 11px;
    padding: 1px 7px;
    border-radius: 20px;
  }

  main{
    max-width: 980px;
    margin: 24px auto 0;
    padding: 0 24px;
  }
  .tab-panel{ display: none; }
  .tab-panel.active{ display: block; }

  .meta-row{
    display:flex;
    gap: 24px;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .meta-item{
    font-size: 13px;
    color: var(--text-dim);
  }
  .meta-item b{
    color: var(--text);
    font-size: 15px;
    display:block;
    font-family: "JetBrains Mono", "SF Mono", Consolas, monospace;
  }

  .empty-state{
    text-align:center;
    padding: 60px 20px;
    color: var(--text-dim);
    border: 1px dashed var(--panel-border);
    border-radius: 10px;
  }

  .match-card{
    background: var(--panel);
    border: 1px solid var(--panel-border);
    border-left: 3px solid var(--neutral);
    border-radius: 8px;
    padding: 18px 20px;
    margin-bottom: 12px;
  }
  .match-card.is-value{
    border-left-color: var(--value);
    box-shadow: 0 0 0 1px var(--value-glow) inset;
  }

  .match-top{
    display:flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 8px;
  }
  .teams{ font-size: 17px; font-weight: 600; }
  .kickoff{ font-size: 12px; color: var(--text-dim); }

  .badge{
    display:inline-block;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 20px;
    letter-spacing: .02em;
  }
  .badge.value{ background: var(--value-glow); color: var(--value); }
  .badge.novalue{ background: rgba(255,255,255,0.05); color: var(--text-dim); }

  table.outcomes{
    width: 100%;
    border-collapse: collapse;
    margin-top: 14px;
    font-size: 13px;
  }
  table.outcomes th{
    text-align: left;
    color: var(--text-dim);
    font-weight: 500;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .04em;
    padding: 4px 8px;
    border-bottom: 1px solid var(--panel-border);
  }
  table.outcomes td{
    padding: 6px 8px;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-family: "JetBrains Mono", "SF Mono", Consolas, monospace;
  }
  table.outcomes tr:last-child td{ border-bottom: none; }
  table.outcomes td.ev-pos{ color: var(--value); font-weight: 600; }
  table.outcomes td.ev-neg{ color: var(--text-dim); }
  table.outcomes td.label{ font-family: inherit; }

  .footer-note{
    max-width: 980px;
    margin: 32px auto 0;
    padding: 0 24px;
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.6;
  }
  .skipped{
    max-width: 980px;
    margin: 20px auto 0;
    padding: 0 24px;
    font-size: 12px;
    color: var(--warn);
  }

  .bankroll-box{
    background: var(--panel);
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 20px;
  }
  .bankroll-top{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    flex-wrap: wrap;
    gap: 16px;
    margin-bottom: 12px;
  }
  .bankroll-figures{ display: flex; gap: 28px; flex-wrap: wrap; }
  .bankroll-figure .label{ font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: .04em; }
  .bankroll-figure .value{ font-size: 22px; font-weight: 700; font-family: "JetBrains Mono", "SF Mono", Consolas, monospace; }
  .bankroll-figure .value.pos{ color: var(--value); }
  .bankroll-figure .value.neg{ color: #e0645a; }
  .bankroll-pending{ font-size: 12px; color: var(--text-dim); }
  .bankroll-chart{ width: 100%; height: 60px; display: block; }
  .bet-log{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
  .bet-log th{
    text-align: left; color: var(--text-dim); font-weight: 500; font-size: 10px;
    text-transform: uppercase; letter-spacing: .04em; padding: 4px 6px;
    border-bottom: 1px solid var(--panel-border);
  }
  .bet-log td{ padding: 5px 6px; border-bottom: 1px solid rgba(255,255,255,0.03); font-family: "JetBrains Mono", "SF Mono", Consolas, monospace; }
  .bet-log td.status-won{ color: var(--value); }
  .bet-log td.status-lost{ color: #e0645a; }
  .bet-log td.status-void{ color: var(--text-dim); font-style: italic; }
  .bet-log td.match-cell{ font-family: inherit; }
</style>
</head>
<body>

<header>
  <h1>Value Radar</h1>
  <div class="sub">Modell-Wahrscheinlichkeiten gegen Buchmacher-Quoten — Fußball &amp; Tennis</div>
</header>

<div class="tabs" id="tabs"></div>
<main id="main"></main>

<div class="footer-note">
  Value = Edge des Modells gegenüber dem no-vig-Marktkonsens, kein garantierter Gewinn.
  Behandle große Abweichungen als Signal zum genaueren Hinschauen (Aufstellung, Form,
  Verletzungen), nicht als automatische Wette. Bei eigenem Einsatz: halber Kelly statt
  voller Kelly, feste Bankroll-Obergrenze.
</div>

<script>
const DATA = __DATA_JSON__;
const TAB_IDS = Object.keys(DATA);

function fmtTime(iso){
  if(!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("de-DE", { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" });
}

function renderMatch(m){
  const card = document.createElement("div");
  card.className = "match-card" + (m.is_value_match ? " is-value" : "");

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

  card.innerHTML = `
    <div class="match-top">
      <div class="teams">${m.home} vs ${m.away}</div>
      <span class="badge ${m.is_value_match ? "value" : "novalue"}">
        ${m.is_value_match ? "VALUE · " + m.best_outcome : "kein Edge"}
      </span>
    </div>
    <div class="kickoff">Anstoss ${fmtTime(m.commence_time)}${m.league ? " · " + m.league : ""} · ${m.bookmaker_count} Buchmacher · Marge ${m.bookmaker_margin_pct.toFixed(1)}%</div>
    <table class="outcomes">
      <thead>
        <tr><th>Ausgang</th><th>Modell</th><th>Quote</th><th>Markt (no-vig)</th><th>Faire Quote</th><th>EV</th><th>Kelly</th></tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;
  return card;
}

function renderSparkline(points){
  if(points.length < 2){
    return '<div style="font-size:12px;color:var(--text-dim);">Noch zu wenig abgerechnete Wetten für eine Kurve.</div>';
  }
  const w = 600, h = 60, pad = 4;
  const min = Math.min(...points), max = Math.max(...points);
  const range = (max - min) || 1;
  const stepX = (w - pad * 2) / (points.length - 1);
  const coords = points.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = points[points.length - 1];
  const first = points[0];
  const lineColor = last >= first ? "#3ddc84" : "#e0645a";
  return `<svg class="bankroll-chart" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <polyline points="${coords}" fill="none" stroke="${lineColor}" stroke-width="2" />
  </svg>`;
}

function renderBankroll(d){
  const bk = d.bankroll;
  const box = document.createElement("div");
  box.className = "bankroll-box";

  const settled = bk.bets.filter(b => b.status === "won" || b.status === "lost");
  const pendingCount = bk.bets.filter(b => b.status === "pending").length;
  const roi = ((bk.current_bankroll - bk.starting_bankroll) / bk.starting_bankroll) * 100;
  const roiClass = roi >= 0 ? "pos" : "neg";

  const curve = [bk.starting_bankroll, ...settled.map(b => b.bankroll_after)];

  const recentRows = settled.slice(-8).reverse().map(b => `
    <tr>
      <td class="match-cell">${b.home} vs ${b.away}</td>
      <td>${b.outcome}</td>
      <td>${b.stake.toFixed(2)}€</td>
      <td>${b.odd.toFixed(2)}</td>
      <td class="status-${b.status}">${b.status === "won" ? "Gewonnen" : "Verloren"}</td>
      <td>${b.bankroll_after.toFixed(2)}€</td>
    </tr>
  `).join("");

  box.innerHTML = `
    <div class="bankroll-top">
      <div class="bankroll-figures">
        <div class="bankroll-figure">
          <div class="label">Bankroll</div>
          <div class="value">${bk.current_bankroll.toFixed(2)}€</div>
        </div>
        <div class="bankroll-figure">
          <div class="label">Start</div>
          <div class="value">${bk.starting_bankroll.toFixed(2)}€</div>
        </div>
        <div class="bankroll-figure">
          <div class="label">ROI</div>
          <div class="value ${roiClass}">${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%</div>
        </div>
      </div>
      <div class="bankroll-pending">${settled.length} abgerechnet · ${pendingCount} offen</div>
    </div>
    ${renderSparkline(curve)}
    ${recentRows ? `<table class="bet-log"><thead><tr>
        <th>Match</th><th>Tipp</th><th>Einsatz</th><th>Quote</th><th>Ergebnis</th><th>Bankroll danach</th>
      </tr></thead><tbody>${recentRows}</tbody></table>` : ""}
  `;
  return box;
}

function renderTabPanel(tabId){
  const d = DATA[tabId];
  const panel = document.createElement("div");
  panel.className = "tab-panel";
  panel.id = "panel-" + tabId;

  panel.appendChild(renderBankroll(d));

  const metaRow = document.createElement("div");
  metaRow.className = "meta-row";
  metaRow.innerHTML = `
    <div class="meta-item">Stand<b>${fmtTime(d.generated_at)}</b></div>
    <div class="meta-item">Geprüft<b>${d.match_count}</b></div>
    <div class="meta-item">Value-Signale<b>${d.value_count}</b></div>
  `;
  panel.appendChild(metaRow);

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
    skip.style.marginTop = "16px";
    skip.style.marginLeft = "0";
    skip.style.marginRight = "0";
    skip.style.padding = "0";
    skip.style.maxWidth = "none";
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
  try { localStorage_unused = true; } catch(e) {}
  window.location.hash = tabId;
}

function init(){
  const tabsEl = document.getElementById("tabs");
  const mainEl = document.getElementById("main");

  TAB_IDS.forEach(tabId => {
    const d = DATA[tabId];
    const btn = document.createElement("button");
    btn.className = "tab-btn";
    btn.id = "tabbtn-" + tabId;
    btn.innerHTML = `${d.label}${d.value_count > 0 ? `<span class="count-pill">${d.value_count}</span>` : ""}`;
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
