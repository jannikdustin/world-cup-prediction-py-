#!/usr/bin/env python3
"""run_value_scan.py — Verbindet odds.json mit dem Dixon-Coles-Modell
(dataset.py + dixon_coles.py + simulation.py) und deiner Value-Logik
(value_oracle.py) zu einem taeglichen Scan.

WICHTIG: Diese Datei muss im selben Ordner liegen wie:
    dataset.py, dixon_coles.py, simulation.py, worldcup2026.py, value_oracle.py
(also im geklonten world-cup-prediction-py Repo, genau wie value_oracle.py selbst).

Kopiere odds.json (Output von fetch_odds.py) ebenfalls in diesen Ordner, oder
passe ODDS_PATH unten an.

Ablauf:
1. Dixon-Coles-Modell einmalig fitten (fit_dixon_coles(load_training_matches()))
   und als aktiven Torfrequenz-Motor injizieren (set_goal_model)
2. Fuer jedes Match aus odds.json: Team-Namen fuzzy auf WC2026_TEAMS matchen
3. Modellwahrscheinlichkeiten berechnen (match_probabilities, neutraler Boden)
4. Gegen die Buchmacher-Quoten pruefen (value_oracle.analyze_value)
5. Alles in results.json schreiben, sortiert nach bestem Edge zuerst

Hinweis Laufzeit: Das Fitten des Modells dauert je nach Datenmenge einige
Sekunden bis wenige Minuten -- das ist in einem GitHub-Actions-Lauf voellig
unkritisch (Standard-Timeout liegt bei 6 Stunden pro Job).

Start:
    python run_value_scan.py
"""

import difflib
import json
import os
import sys
from datetime import datetime, timezone

# run_value_scan.py liegt im Unterordner value_monitor/, aber dataset.py,
# dixon_coles.py, simulation.py, worldcup2026.py und value_oracle.py liegen
# eine Ebene hoeher im Repo-Hauptordner. Python fuegt beim Skriptstart nur
# den eigenen Ordner (value_monitor/) automatisch zum Suchpfad hinzu -- den
# Hauptordner muessen wir deshalb VOR den folgenden Imports manuell ergaenzen.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# --- Imports aus deinem bestehenden Repo (aktuelle Dixon-Coles-Version) ---
try:
    from dataset import load_training_matches
    from dixon_coles import fit_dixon_coles
    from simulation import match_probabilities, set_goal_model
    from worldcup2026 import WC2026_TEAMS, find_team
    from value_oracle import analyze_value
    import bankroll
except ImportError as e:
    print(f"FEHLER beim Import: {e}", file=sys.stderr)
    print("Diese Datei muss im world-cup-prediction-py Ordner liegen, "
          "neben dataset.py / dixon_coles.py / simulation.py / worldcup2026.py "
          "/ value_oracle.py.", file=sys.stderr)
    sys.exit(1)


ODDS_PATH = os.path.join(HERE, "odds.json")
RESULTS_PATH = os.path.join(HERE, "results.json")

# Manuelle Uebersetzungstabelle fuer Faelle, in denen die Odds-API andere
# Namen nutzt als worldcup2026.py (z.B. "USA" vs "United States").
# Bei Bedarf einfach erweitern, sobald dir eine Fehlmeldung auffaellt.
NAME_OVERRIDES = {
    "USA": "United States",
    "South Korea": "Korea Republic",
    "Ivory Coast": "Cote d'Ivoire",
}


def resolve_team(raw_name):
    """Matcht einen Odds-API-Teamnamen auf ein WCTeam-Objekt aus WC2026_TEAMS."""
    lookup_name = NAME_OVERRIDES.get(raw_name, raw_name)

    # 1. exakter Treffer ueber find_team (kennt vermutlich schon Aliase/Codes)
    team = find_team(lookup_name)
    if team is not None:
        return team

    # 2. Fuzzy-Fallback gegen alle Team-Anzeigenamen
    all_names = [t.name for t in WC2026_TEAMS]
    close = difflib.get_close_matches(lookup_name, all_names, n=1, cutoff=0.75)
    if close:
        return find_team(close[0])
    return None


def load_odds():
    if not os.path.exists(ODDS_PATH):
        print(f"FEHLER: {ODDS_PATH} nicht gefunden. Erst fetch_odds.py laufen lassen.",
              file=sys.stderr)
        sys.exit(1)
    with open(ODDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    odds_matches = load_odds()

    print("Fitte Dixon-Coles-Modell auf die letzten 10 Jahre Laenderspiele...")
    model = fit_dixon_coles(load_training_matches())
    set_goal_model(model)
    print("Modell bereit.")

    results = []
    skipped = []

    for m in odds_matches:
        home_team = resolve_team(m["home"])
        away_team = resolve_team(m["away"])

        if not home_team or not away_team:
            skipped.append(f"{m['home']} vs {m['away']} (Team nicht erkannt)")
            continue

        try:
            report = match_probabilities(home_team, away_team)
        except Exception as e:
            skipped.append(f"{m['home']} vs {m['away']} (Modellfehler: {e})")
            continue

        model_probs = [report["p_win_a"], report["p_draw"], report["p_win_b"]]
        rows, margin = analyze_value(model_probs, m["odds"])

        outcome_labels = [f"Sieg {home_team.name}", "Remis", f"Sieg {away_team.name}"]
        best_row = max(rows, key=lambda r: r["ev"])
        best_idx = rows.index(best_row)

        results.append({
            "home": home_team.name,
            "away": away_team.name,
            "sport_key": "soccer_fifa_world_cup",
            "commence_time": m.get("commence_time"),
            "bookmaker_count": m.get("bookmaker_count"),
            "bookmaker_margin_pct": round(margin * 100, 2),
            "expected_goals": f"{report['xg_a']} – {report['xg_b']}",
            "most_likely_score": report["most_likely_score"],
            "outcomes": [
                {
                    "label": outcome_labels[i],
                    "model_prob_pct": round(rows[i]["p"] * 100, 1),
                    "odd": rows[i]["odd"],
                    "novig_prob_pct": round(rows[i]["novig"] * 100, 1),
                    "fair_odd": None if rows[i]["fair_odd"] == float("inf") else round(rows[i]["fair_odd"], 2),
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

    ledger_path = os.path.join(HERE, "ledger_wm.json")
    ledger = bankroll.load_ledger(ledger_path)
    added = bankroll.record_new_bets(ledger, results)
    bankroll.save_ledger(ledger_path, ledger)
    if added:
        print(f"{added} neue Wette(n) ins Bankroll-Ledger eingetragen -> {ledger_path}")

    print(f"{len(results)} Spiele analysiert, davon {output['value_count']} mit Value-Signal.")
    if skipped:
        print(f"{len(skipped)} Spiele uebersprungen:")
        for s in skipped:
            print(f"  - {s}")
    print(f"Ergebnisse gespeichert -> {RESULTS_PATH}")


if __name__ == "__main__":
    main()
