# Value Radar — WM 2026 + Top 5 Ligen & Europa

Automatisiertes Value-Betting-Dashboard, das 1x täglich nachts läuft und zwei
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

Der GitHub-Actions-Workflow führt alle drei Pipelines 1x täglich nachts aus
(01:00 UTC = 02:00 Uhr MEZ / 03:00 Uhr MESZ) und veröffentlicht über GitHub
Pages ein Dashboard mit drei Tabs. Bewusst nur ein Lauf pro Tag: so wird
jedes Spiel/Turnier garantiert nur einmal pro Tag gesehen, und der
Bankroll-Tracker (siehe unten) kann pro Spiel nie versehentlich zweimal
einen Einsatz buchen — neu erschienene Spiele werden zuverlässig beim
nächsten nächtlichen Lauf zum ersten Mal erfasst.

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

### 2. API-Key holen (gilt für alle drei Pipelines)

1. Auf [the-odds-api.com](https://the-odds-api.com) kostenlos registrieren
2. API-Key kopieren

**Kontingent-Rechnung bei 1 Lauf/Tag:** WM 1 Request, Klubs 7 Requests (eine
pro Wettbewerb), Tennis 1–3 Requests (abhängig davon, wie viele Turniere
gerade aktiv sind; die Abfrage, welche Turniere aktiv sind, kostet laut
The-Odds-API-Doku kein Kontingent). Macht zusammen grob 9–11 Requests/Tag
für die reinen Odds-Abrufe. Dazu kommt `settle_bets.py`: 2 Credits pro
Wettbewerb, in dem gerade fällige Wetten abzurechnen sind — typischerweise
0–3 Wettbewerbe gleichzeitig, also 0–6 zusätzliche Credits/Tag. Insgesamt
landest du bei etwa 300–500 Requests/Monat — komfortabel im kostenlosen
500er-Limit, aber nicht mit riesigem Puffer. Falls es doch mal eng wird,
zeigt dir The Odds API das verbleibende Kontingent in jeder Antwort
(`x-requests-remaining`-Header), das taucht auch in den Workflow-Logs auf.

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

Danach committen + pushen. Du bekommst ein Dashboard mit drei Tabs (WM,
Klubs, Tennis) unter einer festen URL. Manueller Test jederzeit über
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

## Tennis-Pipeline (ATP — WTA aktuell nicht abgedeckt)

```
fetch_odds_tennis.py     -> odds_tennis.json     (nur aktuell laufende Turniere, ATP + WTA)
run_value_scan_tennis.py -> results_tennis.json  (Elo aus TennisMyLife-Daten + value_oracle.py)
generate_dashboard.py results_tennis.json dashboard_tennis.html "Value Radar — Tennis ATP"
```

**Datenquelle-Update:** Die ursprünglich geplante Quelle (Jeff Sackmann /
`tennis_atp` + `tennis_wta` auf GitHub) ist nicht mehr öffentlich verfügbar —
beide Repos wurden zwischenzeitlich entfernt. Ersatz ist
[TennisMyLife](https://stats.tennismylife.org) (`stats.tennismylife.org/api/data-files`),
eine aktiv gepflegte, täglich aktualisierte Datenbank im gleichen
Spaltenformat — **deckt aber nur ATP (Herren) ab, keine WTA**.

**Praktische Folge:** `fetch_odds_tennis.py` holt weiterhin Quoten für alle
aktiven Turniere, ATP wie WTA. `run_value_scan_tennis.py` erkennt
WTA-Turniere am Sport-Key und trägt sie klar gekennzeichnet in die
"skipped"-Liste ein, statt sie stillschweigend zu ignorieren oder falsch zu
bewerten. Willst du WTA ergänzen, bräuchte es eine zusätzliche Quelle (z. B.
eine bezahlte Tennis-API) — sag Bescheid, dann bauen wir das nach.

**Warum anders als Fußball/Klubs:**
- **Kein Remis** — Tennis hat nur 2 Ausgänge, `value_oracle.py`s Value-Logik
  funktioniert aber unverändert damit (die Funktionen sind listen-generisch).
- **Rotierende Turnier-Keys** — The Odds API hat keine feste "Tennis-Liga",
  sondern pro Turnier einen eigenen Key, der nur während des Turniers aktiv
  ist. `fetch_odds_tennis.py` fragt deshalb zuerst ab, welche Turniere
  gerade laufen. Läuft gerade kein Turnier, ist `odds_tennis.json` leer —
  das ist normal, kein Fehler.
- **Oberfläche wird geschätzt** — The Odds API liefert keinen Belag direkt.
  `TOURNAMENT_SURFACE_HINTS` in `run_value_scan_tennis.py` ordnet bekannte
  Sand-/Rasen-Turniere anhand des Namens zu, alles andere gilt als Hartplatz.
  Bei Fehleinschätzungen dort ergänzen.
- **Fehlertoleranz eingebaut** — läuft gerade kein Turnier, ist TennisMyLife
  kurz nicht erreichbar, oder tritt ein unerwarteter Fehler auf, schreibt
  das Skript ein leeres Ergebnis statt den ganzen Workflow (inkl. WM-/Klub-
  Dashboard) zu blockieren.

**Lizenzhinweis:** TennisMyLife untersagt Weiterverbreitung/kommerzielle
Nutzung der Rohdatenbank ohne Erlaubnis. Für dein privates Analyse-Tool
unproblematisch; bei Veröffentlichung/Monetarisierung des Dashboards mit
Tennis-Inhalten wäre vorher eine Rückfrage bei TennisMyLife nötig.

## Wichtiger Hinweis

Beide Dashboards zeigen statistische Abweichungen zwischen Modell und Markt,
keine Wettempfehlungen. Große Edges zuerst hinterfragen (Verletzungen,
Aufstellung, Motivation — das kennt kein Modell), Einsätze disziplinieren
(halber statt voller Kelly, feste Bankroll-Grenze) und über die Zeit den CLV
tracken, um zu sehen, ob die Edges echt sind.

## Ein Dashboard statt drei

Alle drei Pipelines (WM, Top-5-Ligen + Europa, Tennis ATP) laufen weiterhin
unabhängig und schreiben ihre eigene `results*.json`. Für die Anzeige gibt es
aber nur noch **ein** Dashboard mit drei Tabs (`generate_combined_dashboard.py`
statt drei separater HTML-Seiten + Verteiler-Startseite). Die Reihenfolge ist
fest WM → Klubs → Tennis, mit einem kleinen grünen Zähler-Badge pro Tab, wenn
dort Value-Treffer vorliegen. Fehlt eine der drei `results*.json`-Dateien
(z. B. weil eine Pipeline gerade nichts gefunden hat), zeigt der jeweilige
Tab einfach "keine Spiele gefunden" statt das ganze Dashboard zu blockieren.
Die alten `generate_dashboard.py`-Einzelseiten bleiben nutzbar (z.B. zum
Testen einzelner Pipelines), werden aber vom Workflow nicht mehr für die
Veröffentlichung verwendet.

## Bankroll-Tracker (Paper Trading)

Jede der drei Pipelines führt jetzt zusätzlich eine eigene, persistente
Bankroll — Start 1.000 €, voller Kelly-Einsatz, nur Signale mit EV > 3 %
zählen als "platzierte Wette". Die drei Bankrolls sind komplett getrennt
(`ledger_wm.json`, `ledger_clubs.json`, `ledger_tennis.json`).

**Neue Dateien:**
- `bankroll.py` — gemeinsames Modul, das neue Value-Signale ins jeweilige
  Ledger einträgt (wird von allen drei `run_value_scan*.py` importiert)
- `settle_bets.py` — prüft nach jedem Lauf, welche Wetten inzwischen
  gespielt sein müssten, holt das Endergebnis über den Scores-Endpoint von
  The Odds API und schreibt Gewinn/Verlust in die Bankroll fort

**So funktioniert die Persistenz:** Da jeder Workflow-Lauf mit einem
frischen Checkout startet, würden die Ledger-Dateien ohne weiteres Zutun bei
jedem Lauf verlorengehen. Der Workflow committet die aktualisierten
`ledger_*.json`-Dateien deshalb am Ende jedes Laufs automatisch zurück ins
Repo (Schritt "Bankroll-Ledger committen"). Das ist der Grund, warum der
Workflow `contents: write`-Rechte braucht (waren schon vorher gesetzt).

**WICHTIG — das ist Paper Trading, kein echtes Geld:** Die Bankroll-Kurve
zeigt, wie sich 1.000 € entwickelt hätten, wenn du bei jedem Signal exakt
den angezeigten Kelly-Anteil gesetzt hättest. Es wird nichts automatisch
wirklich gewettet. Ob (und wie) du das in echtes Wettverhalten überträgst,
liegt bei dir — ich bin kein Finanz- oder Wettberater.

**Grenzen, die du kennen solltest:**
- **3-Tage-Fenster:** The Odds API liefert Endergebnisse nur bis zu 3 Tage
  rückwirkend. Bleibt eine Wette länger offen (z. B. weil der Workflow mal
  ausgefallen ist oder das Ergebnis dort nie erscheint), wird sie nach
  Ablauf des Fensters automatisch "storniert" (`void`) — zählt weder als
  Gewinn noch Verlust, Einsatz wird der Bankroll gutgeschrieben, damit
  nichts für immer in der Schwebe hängt.
- **Team-/Spielernamen-Matching bei der Abrechnung** läuft über exakten
  Namensabgleich zwischen Odds-Endpoint und Scores-Endpoint (beide kommen
  von The Odds API, sollten also übereinstimmen) — bei Abweichungen bleibt
  eine Wette einfach "pending", bis sie ins 3-Tage-Fenster-Timeout läuft.
- **Zusätzliche API-Kosten:** Jeder `settle_bets.py`-Lauf kostet zusätzliche
  Requests (2 Credits pro geprüftem Sport/Wettbewerb mit fälligen Wetten,
  siehe Kontingent-Rechnung oben) — bei nur einem Lauf pro Tag bleibt das
  aber komfortabel im Rahmen.
- **`.gitignore` prüfen:** Falls der Commit-Schritt meldet, die
  `ledger_*.json`-Dateien seien ignoriert, in `.gitignore` nachschauen, ob
  dort pauschal `*.json` o. ä. ausgeschlossen wird, und ggf. eine
  Ausnahme für `value_monitor/ledger_*.json` ergänzen.
