# Value Radar — WM 2026 + Top 5 Ligen & Europa

Automatisiertes Value-Betting-Dashboard, das 3x täglich läuft und zwei
parallele Modelle gegen echte Buchmacherquoten prüft:

- **WM 2026 / Nationalmannschaften** — dein bestehendes Elo+Poisson-Modell (`oracle.py`)
- **Top 5 Ligen + Champions/Europa League** — Wahrscheinlichkeiten direkt von
  [clubelo.com](http://clubelo.com), einer kostenlosen, keyfreien öffentlichen
  Elo-Datenbank für Klubmannschaften, Standard in der Football-Analytics-Szene

Kein manuelles Quoten-Eintippen mehr — du schaust nur noch auf zwei fertige
Dashboards.

## Wie es funktioniert

**WM-Pipeline (Nationalmannschaften):**
```
fetch_odds.py         -> odds.json         (Quoten von The Odds API)
run_value_scan.py     -> results.json      (dein Elo/Poisson-Modell + value_oracle.py)
generate_dashboard.py results.json dashboard.html "Value Radar — WM 2026"
```

**Klub-Pipeline (Top 5 Ligen + Europa):**
```
fetch_odds_clubs.py      -> odds_clubs.json    (Quoten von The Odds API, 7 Wettbewerbe)
run_value_scan_clubs.py  -> results_clubs.json (Wahrscheinlichkeiten direkt von clubelo.com)
generate_dashboard.py results_clubs.json dashboard_clubs.html "Value Radar — Top 5 Ligen + Europa"
```

Beide Pipelines nutzen dieselbe Value-Logik aus `value_oracle.py`
(EV, Kelly, no-vig-Markt) — nur die Quelle der Modell-Wahrscheinlichkeit
unterscheidet sich (eigenes Modell vs. clubelo.com).

Der GitHub-Actions-Workflow führt beide Pipelines 3x täglich (06:00, 12:00,
18:00 UTC) aus und veröffentlicht über GitHub Pages eine Übersichtsseite mit
Links zu beiden Dashboards.

## Warum clubelo.com für Klubs, aber nicht für die WM?

Dein WM-Modell ist auf Länderspiele trainiert (49.500 internationale Spiele)
und kennt keine Klubmannschaften. clubelo.com pflegt eine eigene, seit
Jahrzehnten laufende Elo-Datenbank für Klubs weltweit und stellt unter
`api.clubelo.com/Fixtures` sogar direkt die berechneten Sieg/Remis/Niederlage-
Wahrscheinlichkeiten für alle anstehenden Spiele bereit — kein eigenes Modell
nötig, kein API-Key, komplett kostenlos.

## Setup (einmalig)

### 1. Ordnerstruktur

```
world-cup-prediction-py/
├── oracle.py
├── dataset.py
├── dixon_coles.py
├── simulation.py
├── worldcup2026.py
├── requirements.txt
├── value_oracle.py           <- im Hauptordner, direkt neben oracle.py
└── value_monitor/
    ├── fetch_odds.py
    ├── run_value_scan.py
    ├── fetch_odds_clubs.py
    ├── run_value_scan_clubs.py
    └── generate_dashboard.py
```

**Wichtig:** `value_oracle.py` gehört in den **Hauptordner**, nicht in
`value_monitor/` — genau wie beim allerersten Setup. `run_value_scan.py`
und `run_value_scan_clubs.py` liegen im Unterordner, fügen sich aber beim
Start selbst den Hauptordner zum Python-Suchpfad hinzu (steht so im Code),
damit sie `dataset.py`, `dixon_coles.py`, `simulation.py`, `worldcup2026.py`
und `value_oracle.py` trotzdem importieren können.

**Modell-Hinweis:** Das Repo nutzt inzwischen ein Dixon-Coles-Torfrequenzmodell
(`dixon_coles.py`, recency-gewichtet auf Basis der letzten 10 Jahre
Länderspiele in `dataset.py`) statt des ursprünglichen Elo+Poisson-Ansatzes.
`run_value_scan.py` ist bereits darauf angepasst.

### 2. API-Key holen (nur für Quoten, gilt für beide Pipelines)

1. Auf [the-odds-api.com](https://the-odds-api.com) kostenlos registrieren
2. API-Key kopieren

**Kontingent-Rechnung bei 2 Läufen/Tag:** WM-Pipeline 1 Request, Klub-Pipeline
7 Requests (eine pro Wettbewerb) = 8 Requests × 2 Läufe × 30 Tage ≈ 480/Monat.
Das passt knapp ins kostenlose 500er-Limit von The Odds API.

### 3. Secret in GitHub hinterlegen

**Settings → Secrets and variables → Actions → New repository secret**
- Name: `ODDS_API_KEY`
- Value: dein API-Key
(clubelo.com braucht keinen Key, dafür ist kein zweites Secret nötig)

### 4. Workflow-Datei einfügen

```bash
mkdir -p .github/workflows
mv value_monitor/.github_workflows_value_monitor.yml .github/workflows/value_monitor.yml
```

### 5. GitHub Pages aktivieren

**Settings → Pages → Build and deployment → Source: GitHub Actions**

Danach committen + pushen. Du bekommst eine Übersichtsseite mit zwei Links
(WM-Dashboard, Klub-Dashboard). Manueller Test jederzeit über
**Actions → WM 2026 Value Monitor → Run workflow**.

## Team-Namen-Mismatch

Beide Pipelines matchen Teamnamen automatisch per Fuzzy-Matching plus einer
manuellen Override-Tabelle (`NAME_OVERRIDES` in `run_value_scan.py` bzw.
`run_value_scan_clubs.py`), weil Odds API, clubelo.com und deine
`worldcup2026.py` teils unterschiedliche Schreibweisen nutzen (z. B. "Bayern
Munich" vs. "Bayern", "USA" vs. "United States"). Nicht erkannte Teams landen
in der `skipped`-Liste im jeweiligen Dashboard — taucht dort ein Name auf,
einfach in der passenden Override-Tabelle ergänzen (exakte clubelo-Schreibweise
steht auf clubelo.com/Ranking).

## Phase 2: Tennis

Für Tennis ist automatisierter Odds-Abruf über The Odds API technisch genauso
möglich (Sport-Keys `tennis_atp_wimbledon` etc.), **aber**: dein Prematch-Lab-
Modell braucht Spieler-Formdaten (Aufschlagstatistiken je Belag), die wir
bisher nur manuell recherchiert haben, weil die automatische Datenquelle
(Sackmann-GitHub-Repos) nicht mehr öffentlich verfügbar war. Bevor ich Phase 2
baue, macht es Sinn zu klären, ob wir:

- (a) eine kostenpflichtige Tennis-Stats-API einbinden, oder
- (b) das Modell auf reine Ranking-/Elo-Basis vereinfachen (weniger präzise,
  aber voll automatisierbar wie beim Fußball/Klub-Fußball), oder
- (c) weiterhin mit manueller Dateneingabe pro Turnierwoche arbeiten und nur
  den Odds-Vergleich automatisieren.

Sag Bescheid, sobald Phase 1 läuft — dann gehen wir das an.

## Wichtiger Hinweis

Beide Dashboards zeigen statistische Abweichungen zwischen Modell und Markt,
keine Wettempfehlungen. Große Edges zuerst hinterfragen (Verletzungen,
Aufstellung, Motivation — das kennt kein Modell), Einsätze disziplinieren
(halber statt voller Kelly, feste Bankroll-Grenze) und über die Zeit den CLV
tracken, um zu sehen, ob die Edges echt sind.
