#!/usr/bin/env python3
"""run_value_scan_tennis.py — Baut ein oberflaechen-adjustiertes Elo-Modell
aus historischen ATP-Ergebnissen (TennisMyLife-Database) und prueft
odds_tennis.json auf Value gegen dieses Modell.

ATP-ONLY: Die urspruenglich geplante Datenquelle (Jeff Sackmann /
tennis_atp + tennis_wta auf GitHub) ist nicht mehr oeffentlich verfuegbar
-- beide Repos wurden entfernt. TennisMyLife (stats.tennismylife.org) ist
der aktiv gepflegte Ersatz, deckt aber nur ATP (Herren) ab. WTA-Daten
fehlen deshalb aktuell komplett; WTA-Turniere aus odds_tennis.json landen
automatisch in der "skipped"-Liste, bis eine WTA-Quelle nachgeruestet wird.

Ablauf:
1. Verfuegbare CSV-Dateien ueber die TennisMyLife-API abfragen
   (https://stats.tennismylife.org/api/data-files), nur ATP-Tour-Hauptdraw-
   Dateien der letzten N Jahre laden (Challenger/Quali bewusst aussen vor,
   um naeher am Niveau der odds-gelisteten Matches zu bleiben)
2. Chronologisch durchlaufen, pro Spieler Gesamt- und oberflaechen-
   spezifisches Elo fuehren (identische Logik wie im Fussball-Pendant)
3. Fuer jedes Match aus odds_tennis.json: Spielernamen fuzzy matchen,
   Oberflaeche aus dem Turniernamen ableiten, Sieg-Wahrscheinlichkeit per
   Elo-Formel (geblendet aus Oberflaechen- und Gesamt-Elo)
4. value_oracle.analyze_value gegen die Buchmacher-Quoten (2-Weg, kein Remis)
5. results_tennis.json schreiben, sortiert nach bestem Edge

Voraussetzung: value_oracle.py im Repo-Hauptordner (wird importiert).

Start:
    python run_value_scan_tennis.py
"""

import csv
import difflib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from value_oracle import analyze_value
    import bankroll
except ImportError as e:
    print(f"FEHLER beim Import: {e}", file=sys.stderr)
    print("value_oracle.py muss im Repo-Hauptordner liegen (siehe README).", file=sys.stderr)
    sys.exit(1)


ODDS_PATH = os.path.join(HERE, "odds_tennis.json")
RESULTS_PATH = os.path.join(HERE, "results_tennis.json")

TML_FILES_API = "https://stats.tennismylife.org/api/data-files"
TRAINING_YEARS = 8
CURRENT_YEAR = datetime.now().year

ELO_START = 1500.0
K_FACTOR = 32.0
SURFACE_WEIGHT = 0.65
MIN_SURFACE_MATCHES = 3

TOURNAMENT_SURFACE_HINTS = {
    "french open": "Clay", "roland garros": "Clay",
    "madrid": "Clay", "rome": "Clay", "italian open": "Clay",
    "monte carlo": "Clay", "barcelona": "Clay", "hamburg": "Clay",
    "wimbledon": "Grass", "queen's": "Grass", "halle": "Grass",
    "eastbourne": "Grass", "s-hertogenbosch": "Grass", "mallorca": "Grass",
}


def resolve_surface(tournament_name):
    name_lower = tournament_name.lower()
    for hint, surface in TOURNAMENT_SURFACE_HINTS.items():
        if hint in name_lower:
            return surface
    return "Hard"


def fetch_json(url, retries=3, timeout=20):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "value-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"{url} nach {retries} Versuchen nicht erreichbar: {last_error}")


def fetch_csv_text(url, retries=3, timeout=30):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "value-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last_error = e
            time.sleep(2 * attempt)
    print(f"  Konnte {url} nicht laden: {last_error}", file=sys.stderr)
    return None


def load_training_matches():
    """Laedt ATP-Tour-Hauptdraw-Matches der letzten TRAINING_YEARS Jahre von
    TennisMyLife. Gibt eine chronologisch sortierte Liste von dicts zurueck:
    {date, surface, winner, loser}."""
    print(f"  Frage Dateiliste bei TennisMyLife ab ({TML_FILES_API}) ...")
    file_index = fetch_json(TML_FILES_API)
    files = file_index.get("files", [])

    # Nur Haupt-Tour-Dateien im Muster "YYYY.csv" (kein "_challenger",
    # "_quali", "ongoing_tourneys" etc.) und nur die letzten TRAINING_YEARS Jahre.
    wanted_years = {str(y) for y in range(CURRENT_YEAR - TRAINING_YEARS, CURRENT_YEAR + 1)}
    tour_files = [
        f for f in files
        if f.get("name", "").replace(".csv", "") in wanted_years
    ]
    print(f"  {len(tour_files)} passende Jahres-Dateien gefunden: "
          f"{[f['name'] for f in tour_files]}")

    matches = []
    for f in tour_files:
        print(f"  Lade {f['name']} ...")
        text = fetch_csv_text(f["url"])
        if text is None:
            continue

        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            try:
                matches.append({
                    "date": row.get("tourney_date", ""),
                    "surface": row.get("surface") or "Hard",
                    "winner": row["winner_name"],
                    "loser": row["loser_name"],
                })
                count += 1
            except KeyError:
                continue
        print(f"    {count} Matches geladen.")

    matches.sort(key=lambda m: m["date"])
    return matches


class EloBook:
    """Fuehrt Gesamt- und Oberflaechen-Elo pro Spieler."""

    def __init__(self):
        self.overall = {}
        self.surface = {}
        self._surface_counts = {}

    def get_overall(self, name):
        return self.overall.get(name, ELO_START)

    def get_surface(self, name, surface):
        return self.surface.get((name, surface), ELO_START)

    def blended_rating(self, name, surface):
        n = self._surface_counts.get((name, surface), 0)
        surf_r = self.get_surface(name, surface)
        overall_r = self.get_overall(name)
        if n < MIN_SURFACE_MATCHES:
            return overall_r
        return SURFACE_WEIGHT * surf_r + (1 - SURFACE_WEIGHT) * overall_r

    def replay(self, matches):
        for m in matches:
            winner, loser, surface = m["winner"], m["loser"], m["surface"]

            r_w_overall = self.get_overall(winner)
            r_l_overall = self.get_overall(loser)
            r_w_surf = self.get_surface(winner, surface)
            r_l_surf = self.get_surface(loser, surface)

            exp_w_overall = 1.0 / (1.0 + 10 ** ((r_l_overall - r_w_overall) / 400))
            exp_w_surf = 1.0 / (1.0 + 10 ** ((r_l_surf - r_w_surf) / 400))

            self.overall[winner] = r_w_overall + K_FACTOR * (1 - exp_w_overall)
            self.overall[loser] = r_l_overall + K_FACTOR * (0 - (1 - exp_w_overall))
            self.surface[(winner, surface)] = r_w_surf + K_FACTOR * (1 - exp_w_surf)
            self.surface[(loser, surface)] = r_l_surf + K_FACTOR * (0 - (1 - exp_w_surf))

            self._surface_counts[(winner, surface)] = self._surface_counts.get((winner, surface), 0) + 1
            self._surface_counts[(loser, surface)] = self._surface_counts.get((loser, surface), 0) + 1


def resolve_player(raw_name, known_names):
    if raw_name in known_names:
        return raw_name
    close = difflib.get_close_matches(raw_name, known_names, n=1, cutoff=0.82)
    return close[0] if close else None


def load_odds():
    if not os.path.exists(ODDS_PATH):
        print(f"FEHLER: {ODDS_PATH} nicht gefunden. Erst fetch_odds_tennis.py laufen lassen.",
              file=sys.stderr)
        sys.exit(1)
    with open(ODDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_empty_result(reason):
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "match_count": 0,
        "value_count": 0,
        "skipped": [reason],
        "matches": [],
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)


def main():
    odds_matches = load_odds()

    if not odds_matches:
        print("Keine aktiven Tennis-Turniere/Quoten gefunden -- schreibe leeres Ergebnis.")
        write_empty_result("Kein Turnier aktiv, keine Quoten von The Odds API erhalten.")
        return

    print(f"Lade ATP-Trainingsdaten (letzte {TRAINING_YEARS} Jahre, TennisMyLife) ...")
    try:
        matches = load_training_matches()
    except RuntimeError as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        write_empty_result(f"TennisMyLife nicht erreichbar: {e}")
        return

    print(f"{len(matches)} historische ATP-Matches geladen.")

    if not matches:
        write_empty_result("Keine ATP-Trainingsdaten geladen (TennisMyLife leer/nicht erreichbar).")
        return

    print("Berechne Elo-Ratings (chronologisch, oberflaechenadjustiert) ...")
    book = EloBook()
    book.replay(matches)
    known_names = sorted(set(book.overall.keys()))

    results = []
    skipped = []

    for m in odds_matches:
        # WTA-Turniere koennen wir mangels Trainingsdaten aktuell nicht
        # bewerten -- klar als solche kennzeichnen statt sie als "Spieler
        # nicht erkannt" zu verstecken.
        if "wta" in m.get("tournament_key", "").lower():
            skipped.append(f"{m['player_a']} vs {m['player_b']} ({m['tournament']}) — "
                            f"WTA aktuell nicht abgedeckt (keine Trainingsdaten)")
            continue

        a_resolved = resolve_player(m["player_a"], known_names)
        b_resolved = resolve_player(m["player_b"], known_names)

        if not a_resolved or not b_resolved:
            skipped.append(f"{m['player_a']} vs {m['player_b']} ({m['tournament']}) — Spieler nicht erkannt")
            continue

        surface = resolve_surface(m["tournament"])
        r_a = book.blended_rating(a_resolved, surface)
        r_b = book.blended_rating(b_resolved, surface)
        p_a = 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400))
        p_b = 1.0 - p_a

        model_probs = [p_a, p_b]
        rows, margin = analyze_value(model_probs, m["odds"])

        outcome_labels = [f"Sieg {a_resolved}", f"Sieg {b_resolved}"]
        best_row = max(rows, key=lambda r: r["ev"])
        best_idx = rows.index(best_row)

        results.append({
            "home": a_resolved,
            "away": b_resolved,
            "league": f"{m['tournament']} ({surface})",
            "sport_key": m.get("tournament_key"),
            "commence_time": m.get("commence_time"),
            "bookmaker_count": m.get("bookmaker_count"),
            "bookmaker_margin_pct": round(margin * 100, 2),
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
                for i in range(2)
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

    ledger_path = os.path.join(HERE, "ledger_tennis.json")
    ledger = bankroll.load_ledger(ledger_path)
    added = bankroll.record_new_bets(ledger, results)
    bankroll.save_ledger(ledger_path, ledger)
    if added:
        print(f"{added} neue Wette(n) ins Bankroll-Ledger eingetragen -> {ledger_path}")

    print(f"{len(results)} Matches analysiert, davon {output['value_count']} mit Value-Signal.")
    if skipped:
        print(f"{len(skipped)} Matches uebersprungen:")
        for s in skipped:
            print(f"  - {s}")
    print(f"Ergebnisse gespeichert -> {RESULTS_PATH}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FEHLER (unerwartet): {e}", file=sys.stderr)
        write_empty_result(f"Unerwarteter Fehler: {e}")
