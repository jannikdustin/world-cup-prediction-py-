#!/usr/bin/env python3
"""run_value_scan_clubs.py — Verbindet odds_clubs.json mit den fertigen

Sieg/Remis/Niederlage-Wahrscheinlichkeiten von clubelo.com.

Unterstützt Top-5-Ligen, Europapokal sowie die 2. Bundesliga.

Ablauf:
1. api.clubelo.com/Fixtures abrufen (kein Key noetig)
   -> CSV mit Tordifferenz-Wahrscheinlichkeiten pro kommendem Spiel
2. Heimsieg = Summe aller GD>0 Spalten, Remis = GD=0, Auswaertssieg = Summe aller GD<0
3. Team-Namen zwischen Odds-API und ClubElo abgleichen (Fuzzy + Override-Tabelle)
4. value_oracle.analyze_value gegen die Buchmacher-Quoten aus odds_clubs.json
5. results_clubs.json schreiben, sortiert nach bestem Edge

Start:
    python run_value_scan_clubs.py
"""

import csv
from datetime import datetime, timezone
import difflib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

# run_value_scan_clubs.py liegt im Unterordner value_monitor/, aber
# value_oracle.py liegt eine Ebene hoeher im Repo-Hauptordner.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    import bankroll
    from value_oracle import analyze_value
except ImportError as e:
    print(f"FEHLER beim Import: {e}", file=sys.stderr)
    print(
        "value_oracle.py muss im Repo-Hauptordner liegen (siehe README).",
        file=sys.stderr,
    )
    sys.exit(1)


ODDS_PATH = os.path.join(HERE, "odds_clubs.json")
RESULTS_PATH = os.path.join(HERE, "results_clubs.json")
CLUBELO_FIXTURES_URL = "https://api.clubelo.com/Fixtures"

# Manuelle Uebersetzungstabelle: Odds-API-Name -> ClubElo-Name.
# Erweitert um gängige Teams der Bundesliga & 2. Bundesliga.
NAME_OVERRIDES = {
    # 1. Bundesliga
    "Bayern Munich": "Bayern",
    "Borussia Dortmund": "Dortmund",
    "Bayer Leverkusen": "Leverkusen",
    "RB Leipzig": "RBLeipzig",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "VfB Stuttgart": "Stuttgart",
    "Borussia Monchengladbach": "Gladbach",
    "Borussia Mönchengladbach": "Gladbach",
    "VfL Wolfsburg": "Wolfsburg",
    "SC Freiburg": "Freiburg",
    "1. FC Union Berlin": "Union Berlin",
    "FC Augsburg": "Augsburg",
    "SV Werder Bremen": "Werder",
    "TSG 1899 Hoffenheim": "Hoffenheim",
    "1. FSV Mainz 05": "Mainz",
    "1. FC Heidenheim": "Heidenheim",
    "FC St. Pauli": "St Pauli",
    "VfL Bochum": "Bochum",
    "Holstein Kiel": "Holstein",
    # 2. Bundesliga & Wechslermannschaften
    "Hamburger SV": "Hamburg",
    "FC Schalke 04": "Schalke",
    "1. FC Köln": "Köln",
    "Hertha BSC": "Hertha",
    "Fortuna Düsseldorf": "Düsseldorf",
    "Hannover 96": "Hannover",
    "1. FC Kaiserslautern": "Lautern",
    "1. FC Nürnberg": "Nürnberg",
    "Karlsruher SC": "Karlsruhe",
    "SC Paderborn 07": "Paderborn",
    "SV Elversberg": "Elversberg",
    "SV Darmstadt 98": "Darmstadt",
    "SpVgg Greuther Fürth": "Fürth",
    "1. FC Magdeburg": "Magdeburg",
    "Eintracht Braunschweig": "Braunschweig",
    "SSV Ulm 1846": "Ulm",
    "SSV Jahn Regensburg": "Regensburg",
    "Preußen Münster": "Münster",
    "Arminia Bielefeld": "Bielefeld",
    "SV Wehen Wiesbaden": "Wiesbaden",
    "FC Hansa Rostock": "Rostock",
    "VfL Osnabrück": "Osnabrück",
    # Internationale Top-Teams
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Tottenham Hotspur": "Tottenham",
    "Newcastle United": "Newcastle",
    "Wolverhampton Wanderers": "Wolves",
    "Brighton and Hove Albion": "Brighton",
    "West Ham United": "West Ham",
    "Nottingham Forest": "Nott'm Forest",
    "Real Madrid": "Real Madrid",
    "Atletico Madrid": "Atletico",
    "Real Sociedad": "Sociedad",
    "Athletic Bilbao": "Ath Bilbao",
    "Inter Milan": "Inter",
    "AC Milan": "Milan",
    "AS Roma": "Roma",
    "Paris Saint Germain": "Paris SG",
    "Olympique Marseille": "Marseille",
    "Olympique Lyonnais": "Lyon",
}


def fetch_clubelo_fixtures(max_retries=3, base_delay=5):
    """Laedt Fixtures-CSV von ClubElo, mit Retry bei kurzzeitigen

    Verbindungsproblemen. Gibt eine Liste von dicts zurueck.
    """
    req = urllib.request.Request(
        CLUBELO_FIXTURES_URL, headers={"User-Agent": "value-monitor/1.0"}
    )

    last_error = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                text = resp.read().decode("utf-8")
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            print(
                f"  Versuch {attempt}/{max_retries} fehlgeschlagen ({e}), "
                f"warte {base_delay * attempt}s ...",
                file=sys.stderr,
            )
            if attempt < max_retries:
                time.sleep(base_delay * attempt)
    else:
        raise RuntimeError(
            f"clubelo.com nach {max_retries} Versuchen nicht erreichbar: {last_error}"
        )

    reader = csv.DictReader(io.StringIO(text))
    fixtures = []
    for row in reader:
        try:
            positive_cols = ["GD=1", "GD=2", "GD=3", "GD=4", "GD=5", "GD>5"]
            negative_cols = [
                "GD<-5",
                "GD=-5",
                "GD=-4",
                "GD=-3",
                "GD=-2",
                "GD=-1",
            ]

            p_home = sum(float(row[c]) for c in positive_cols)
            p_draw = float(row["GD=0"])
            p_away = sum(float(row[c]) for c in negative_cols)

            total = p_home + p_draw + p_away
            if total > 0:
                p_home, p_draw, p_away = (
                    p_home / total,
                    p_draw / total,
                    p_away / total,
                )

            fixtures.append({
                "date": row["Date"],
                "country": row["Country"],
                "home": row["Home"],
                "away": row["Away"],
                "probs": [p_home, p_draw, p_away],
            })
        except (KeyError, ValueError):
            continue

    return fixtures


def resolve_and_match(odds_home, odds_away, fixtures):
    """Findet das passende ClubElo-Fixture fuer ein Odds-API-Match."""
    home_lookup = NAME_OVERRIDES.get(odds_home, odds_home)
    away_lookup = NAME_OVERRIDES.get(odds_away, odds_away)

    clubelo_names = list(
        {f["home"] for f in fixtures} | {f["away"] for f in fixtures}
    )

    def best_match(name):
        if name in clubelo_names:
            return name
        close = difflib.get_close_matches(name, clubelo_names, n=1, cutoff=0.72)
        return close[0] if close else None

    home_resolved = best_match(home_lookup)
    away_resolved = best_match(away_lookup)

    if not home_resolved or not away_resolved:
        return None

    for f in fixtures:
        if f["home"] == home_resolved and f["away"] == away_resolved:
            return f
    return None


def load_odds():
    if not os.path.exists(ODDS_PATH):
        print(
            f"FEHLER: {ODDS_PATH} nicht gefunden. Erst fetch_odds_clubs.py"
            " laufen lassen.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(ODDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    odds_matches = load_odds()
    print("Lade Fixture-Wahrscheinlichkeiten von clubelo.com ...")
    try:
        fixtures = fetch_clubelo_fixtures()
    except RuntimeError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        print(
            "Schreibe leeres Ergebnis, damit der Workflow trotzdem fortfahren"
            " kann.",
            file=sys.stderr,
        )
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "match_count": 0,
            "value_count": 0,
            "skipped": [f"clubelo.com nicht erreichbar: {e}"],
            "matches": [],
        }
        with open(RESULTS_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        return

    print(f"{len(fixtures)} anstehende Spiele bei ClubElo gefunden.")

    results = []
    skipped = []

    for m in odds_matches:
        fixture = resolve_and_match(m["home"], m["away"], fixtures)
        if not fixture:
            skipped.append(
                f"{m['home']} vs {m['away']} ({m['league']}) — kein"
                " ClubElo-Match"
            )
            continue

        rows, margin = analyze_value(fixture["probs"], m["odds"])

        outcome_labels = [f"Sieg {m['home']}", "Remis", f"Sieg {m['away']}"]
        best_row = max(rows, key=lambda r: r["ev"])
        best_idx = rows.index(best_row)

        results.append({
            "home": m["home"],
            "away": m["away"],
            "league": m["league"],
            "sport_key": m.get("sport_key"),
            "commence_time": m.get("commence_time"),
            "bookmaker_count": m.get("bookmaker_count"),
            "bookmaker_margin_pct": round(margin * 100, 2),
            "outcomes": [
                {
                    "label": outcome_labels[i],
                    "model_prob_pct": round(rows[i]["p"] * 100, 1),
                    "odd": rows[i]["odd"],
                    "novig_prob_pct": round(rows[i]["novig"] * 100, 1),
                    "fair_odd": (
                        None
                        if rows[i]["fair_odd"] == float("inf")
                        else round(rows[i]["fair_odd"], 2)
                    ),
                    "ev_pct": round(rows[i]["ev"] * 100, 1),
                    "kelly_pct": round(rows[i]["kelly"] * 100, 1),
                    "is_value": rows[i]["value"],
                }
                for i in range(3)
            ],
            "best_outcome": outcome_labels[best_idx],
            "best_ev_pct": round(best_row["ev"] * 100, 1),
            "is_value_match": best_row["value"],
        })

    results.sort(key=lambda r: r["best_ev_pct"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "match_count": len(results),
        "value_count": sum(1 for r in results if r["is_value_match"]),
        "skipped": skipped,
        "matches": results,
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    ledger_path = os.path.join(HERE, "ledger_clubs.json")
    ledger = bankroll.load_ledger(ledger_path)
    added = bankroll.record_new_bets(ledger, results)
    bankroll.save_ledger(ledger_path, ledger)
    if added:
        print(
            f"{added} neue Wette(n) ins Bankroll-Ledger eingetragen ->"
            f" {ledger_path}"
        )

    print(
        f"{len(results)} Spiele analysiert, davon {output['value_count']} mit"
        " Value-Signal."
    )
    if skipped:
        print(
            f"{len(skipped)} Spiele uebersprungen (Team-Namen nicht gematcht):"
        )
        for s in skipped:
            print(f"  - {s}")
    print(f"Ergebnisse gespeichert -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
