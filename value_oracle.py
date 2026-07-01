#!/usr/bin/env python3
"""World Cup Oracle — Value Edition.

Erweiterung rund um oracle.py: manuelle Buchmacher-Quoten + Value-Erkennung.
Du tippst eine Partie plus drei 1X2-Quoten ein und bekommst zusaetzlich zur
Modell-Vorhersage: faire Quote, markt-implizite Wahrscheinlichkeit ohne Marge
(no-vig), Edge (Expected Value) und einen Kelly-Einsatzvorschlag.

Beispiel im Prompt (Reihenfolge der Quoten: Heimsieg  Remis  Auswaertssieg):
    > Germany vs France 3.20 3.50 2.10

Reine Vorhersage ohne Quoten geht weiterhin:
    > Germany vs France

Deutsche Kommaquoten (3,20) werden ebenso akzeptiert wie 3.20.

WICHTIG: implied_from_odds() und analyze_value() haben KEINE Abhaengigkeit
zum Prognosemodell -- sie nehmen fertige Wahrscheinlichkeiten als Parameter
entgegen. Andere Skripte (z.B. run_value_scan.py) importieren nur diese
beiden Funktionen und funktionieren deshalb unabhaengig davon, wie das
Modell im Repo gerade heisst oder aufgebaut ist.

Aktuelles Modell in diesem Repo: Dixon-Coles-Torfrequenzmodell (dixon_coles.py),
recency- und wettbewerbsgewichtet auf Basis der letzten 10 Jahre Laenderspiele
(dataset.py), injiziert in simulation.py ueber set_goal_model().

Start:
    python value_oracle.py    # interaktiver Modus, fitted das Modell einmalig
"""

import argparse
import sys

from dataset import load_training_matches
from dixon_coles import fit_dixon_coles
from simulation import match_probabilities, set_goal_model
from worldcup2026 import WC2026_TEAMS, find_team


MODEL = None


# ---------- Value-Mathematik (modellunabhaengig, immer verfuegbar) ----------

def implied_from_odds(odds):
    """odds = [home, draw, away] dezimal. Liefert raw-implied, Marge, no-vig."""
    raw = [1.0 / o for o in odds]
    overround = sum(raw)              # > 1.0, enthaelt die Buchmacher-Marge
    margin = overround - 1.0
    novig = [r / overround for r in raw]
    return raw, margin, novig


def analyze_value(model_probs, odds):
    """model_probs = [p_home, p_draw, p_away]. Pro Ausgang: faire Quote,
    no-vig-Prob, Edge (EV), Kelly, Value-Flag."""
    _, margin, novig = implied_from_odds(odds)
    rows = []
    for p, o, q_nv in zip(model_probs, odds, novig):
        fair_odd = (1.0 / p) if p > 0 else float("inf")
        ev = p * o - 1.0                       # Expected Value je Einsatz-Einheit
        kelly = (ev / (o - 1.0)) if o > 1.0 else 0.0
        rows.append({
            "p": p,
            "odd": o,
            "novig": q_nv,
            "fair_odd": fair_odd,
            "ev": ev,
            "kelly": max(kelly, 0.0),
            "value": ev > 0,
        })
    return rows, margin


def fmt_odd(o):
    return "-" if o == float("inf") else f"{o:.2f}"


# ---------- Eingabe-Parsing (nur fuer interaktiven Modus) ----------

def peel_odds(tokens):
    """Loest hintere Dezimal-Quoten ab (akzeptiert Komma). Gibt (name_tokens, odds)."""
    def to_float(tok):
        tok = tok.replace(",", ".")
        try:
            return float(tok)
        except ValueError:
            return None

    if len(tokens) >= 3:
        maybe_odds = [to_float(t) for t in tokens[-3:]]
        if all(v is not None for v in maybe_odds):
            return tokens[:-3], maybe_odds
    return tokens, None


def parse_matchup(line):
    """'Germany vs France [odds odds odds]' -> (home_str, away_str, odds|None)."""
    tokens = line.strip().split()
    tokens, odds = peel_odds(tokens)

    lowered = [t.lower() for t in tokens]
    if "vs" not in lowered:
        return None, None, None
    idx = lowered.index("vs")
    home_tokens = tokens[:idx]
    away_tokens = tokens[idx + 1:]
    if not home_tokens or not away_tokens:
        return None, None, None
    return " ".join(home_tokens), " ".join(away_tokens), odds


def print_result(a, b, report, odds=None):
    p_home, p_draw, p_away = report["p_win_a"], report["p_draw"], report["p_win_b"]
    print(f"\n{a.name} vs {b.name}")
    print(f"  Modell:  Sieg {a.name}: {p_home*100:.1f}%   Remis: {p_draw*100:.1f}%   Sieg {b.name}: {p_away*100:.1f}%")
    print(f"  Erwartete Tore: {a.name} {report['xg_a']}  –  {report['xg_b']} {b.name}")
    print(f"  Wahrscheinlichstes Ergebnis: {report['most_likely_score']}")

    if odds is None:
        return

    model_probs = [p_home, p_draw, p_away]
    rows, margin = analyze_value(model_probs, odds)
    labels = [f"Sieg {a.name}", "Remis", f"Sieg {b.name}"]
    print(f"  Buchmacher-Marge: {margin*100:.2f}%")
    print(f"  {'Ausgang':<14} {'Quote':>7} {'Modell':>8} {'no-vig':>8} {'Faire Q.':>9} {'EV':>8} {'Kelly':>7}  Value?")
    for label, r in zip(labels, rows):
        flag = "  <-- VALUE" if r["value"] else ""
        print(f"  {label:<14} {r['odd']:>7.2f} {r['p']*100:>7.1f}% {r['novig']*100:>7.1f}% "
              f"{fmt_odd(r['fair_odd']):>9} {r['ev']*100:>+7.1f}% {r['kelly']*100:>6.1f}%{flag}")


def main():
    parser = argparse.ArgumentParser(description="World Cup Oracle — Value Edition")
    args = parser.parse_args()

    global MODEL
    print("Fitte Dixon-Coles-Modell auf die letzten 10 Jahre Laenderspiele...")
    MODEL = fit_dixon_coles(load_training_matches())
    set_goal_model(MODEL)
    print("Modell bereit.\n")

    print("Eingabe: 'Team A vs Team B' oder 'Team A vs Team B QuoteHeim QuoteRemis QuoteAusw' (leer = Ende)")
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            break
        if not line:
            break

        home_str, away_str, odds = parse_matchup(line)
        if home_str is None:
            print("  Konnte die Zeile nicht lesen. Format: 'Team A vs Team B [Q1 Q2 Q3]'")
            continue

        a = find_team(home_str)
        b = find_team(away_str)
        if a is None:
            print(f"  ! Unbekanntes Team: '{home_str}'")
            continue
        if b is None:
            print(f"  ! Unbekanntes Team: '{away_str}'")
            continue

        try:
            report = match_probabilities(a, b)
        except Exception as e:
            print(f"  Modellfehler: {e}")
            continue

        print_result(a, b, report, odds)


if __name__ == "__main__":
    main()
