#!/usr/bin/env python3
"""generate_dashboard.py — Baut dashboard.html aus results.json.

Liest results.json (Output von run_value_scan.py) und rendert ein
eigenstaendiges, offline funktionierendes Dashboard. Die Daten werden
direkt ins HTML eingebettet (kein fetch() noetig, funktioniert auch
per Doppelklick lokal oder ueber GitHub Pages).

Start:
    python generate_dashboard.py
"""

import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))

# Standardmaessig WM-Pipeline (results.json -> dashboard.html), fuer die
# Klub-Pipeline aufrufen mit:
#   python generate_dashboard.py results_clubs.json dashboard_clubs.html "Value Radar — Top 5 Ligen + Europa"
RESULTS_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "results.json")
OUT_PATH = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "dashboard.html")
TITLE = sys.argv[3] if len(sys.argv) > 3 else "Value Radar — WM 2026"


def main():
    with open(RESULTS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    data_json = json.dumps(data, ensure_ascii=False)

    html = HTML_TEMPLATE.replace("__DATA_JSON__", data_json)
    html = html.replace("__TITLE__", TITLE)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard erzeugt -> {OUT_PATH}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
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
  .mono{ font-family: "JetBrains Mono", "SF Mono", Consolas, monospace; }

  header{
    padding: 40px 24px 28px;
    border-bottom: 1px solid var(--panel-border);
    max-width: 980px;
    margin: 0 auto;
  }
  header h1{
    font-size: 28px;
    margin: 0 0 6px 0;
    letter-spacing: -0.02em;
  }
  header .sub{
    color: var(--text-dim);
    font-size: 14px;
  }
  .meta-row{
    display:flex;
    gap: 24px;
    margin-top: 18px;
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
    font-family: "JetBrains Mono", monospace;
  }

  main{
    max-width: 980px;
    margin: 28px auto 0;
    padding: 0 24px;
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
    transition: border-color .15s ease;
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
    font-family: "JetBrains Mono", monospace;
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
</style>
</head>
<body>

<header>
  <h1>__TITLE__</h1>
  <div class="sub">Modell-Wahrscheinlichkeiten (Elo + Poisson) gegen Buchmacher-Quoten</div>
  <div class="meta-row">
    <div class="meta-item">Stand<b id="stat-time">—</b></div>
    <div class="meta-item">Spiele geprueft<b id="stat-count">—</b></div>
    <div class="meta-item">Value-Signale<b id="stat-value">—</b></div>
  </div>
</header>

<main id="main"></main>
<div class="skipped" id="skipped"></div>

<div class="footer-note">
  Value = Edge des Modells gegenueber dem no-vig-Marktkonsens, kein garantierter Gewinn.
  Behandle grosse Abweichungen als Signal zum genaueren Hinschauen (Aufstellung, Form,
  Verletzungen), nicht als automatische Wette. Bei eigenem Einsatz: halber Kelly statt
  voller Kelly, feste Bankroll-Obergrenze.
</div>

<script>
const DATA = __DATA_JSON__;

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

function render(){
  document.getElementById("stat-time").textContent = fmtTime(DATA.generated_at);
  document.getElementById("stat-count").textContent = DATA.match_count;
  document.getElementById("stat-value").textContent = DATA.value_count;

  const main = document.getElementById("main");
  if(!DATA.matches || DATA.matches.length === 0){
    main.innerHTML = '<div class="empty-state">Keine Spiele mit vollstaendigem Quotenmarkt gefunden.</div>';
    return;
  }
  DATA.matches.forEach(m => main.appendChild(renderMatch(m)));

  if(DATA.skipped && DATA.skipped.length){
    document.getElementById("skipped").textContent =
      "Uebersprungen: " + DATA.skipped.join(" · ");
  }
}

render();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
