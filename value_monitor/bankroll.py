#!/usr/bin/env python3
"""bankroll.py — Gemeinsames Modul fuer die drei Paper-Trading-Bankrolls
(WM, Klubs, Tennis). Wird von den run_value_scan*.py-Skripten importiert,
um neue Value-Signale als "platzierte Wette" in ein persistentes Ledger
(ledger_<pipeline>.json) einzutragen, und von settle_bets.py, um diese
Wetten nach Spielende abzurechnen.

WICHTIG: Das ist ein SIMULIERTER Tracker (Paper Trading) auf Basis der vom
Modell errechneten Value-Signale -- es wird kein echtes Geld eingesetzt und
keine echte Wette platziert. Die Bankroll-Kurve zeigt, wie sich 1.000 EUR
entwickelt HAETTEN, wenn du jedes Mal exakt den angezeigten Kelly-Anteil
gesetzt haettest.

BANKROLL-SEMANTIK -- current_bankroll ist der LIVE-KONTOSTAND (verfuegbares
Geld), kein reiner "nur abgerechnete Wetten"-Wert:
- Beim Platzieren einer Wette wird der Einsatz SOFORT von current_bankroll
  abgezogen (das Geld ist "gebunden", genau wie bei einem echten Konto).
- Bei Gewinn (settle_bets.py) wird der volle Payout (Einsatz x Quote)
  wieder gutgeschrieben.
- Bei Verlust passiert nichts weiter (der Einsatz bleibt abgezogen).
- Bei Stornierung (void, z.B. Ergebnis nicht mehr abrufbar) wird der
  Einsatz zurueckerstattet.
current_bankroll + Summe aller offenen Einsaetze (siehe Dashboard "Im
Einsatz") ergibt den Gesamtwert (current_bankroll VOR Abzug offener Wetten).

Design-Entscheidungen (siehe README fuer Details):
- Voller Kelly-Einsatz (nicht halber)
- Drei komplett getrennte Bankrolls (WM / Klubs / Tennis), je eigene
  ledger_<pipeline>.json
- Nur Signale mit EV > EV_THRESHOLD_PCT gelten als "platzierte Wette"
- Nur Quote >= MIN_ODD gilt als "platzierte Wette"
- Ein Match+Ausgang wird nur EINMAL geloggt (beim ersten Erscheinen als
  qualifizierendes Signal), auch wenn der Workflow mehrmals taeglich laeuft
  und dasselbe Spiel in mehreren Laeufen auftaucht
"""

import hashlib
import json
import os
from datetime import datetime, timezone

STARTING_BANKROLL = 1000.0
EV_THRESHOLD_PCT = 3.0  # nur Signale oberhalb dieser EV-Schwelle werden "gesetzt"
MIN_ODD = 1.4  # unterhalb dieser Quote wird NIE gesetzt, auch bei Value

# Odds-API-Scores-Endpoint kann nur bis zu 3 Tage zurueckblicken -- Wetten,
# die laenger als das offen sind (z.B. weil der Workflow mal ausgefallen
# ist), koennen wir nicht mehr sicher abrechnen und markieren sie als "void".
MAX_SETTLEMENT_WINDOW_DAYS = 3


def _bet_id(home, away, commence_time):
    """Stabile ID PRO SPIEL (nicht pro Tipp!). Bewusst OHNE outcome_label:
    wuerde sich zwischen zwei taeglichen Laeufen der Quotenstand so
    verschieben, dass ein anderer Ausgang zum Value-Pick wird, soll das
    NICHT als zweite Wette auf dasselbe Spiel gezaehlt werden. Ein Spiel
    bekommt maximal einen Eintrag im Ledger, so wie es beim allerersten
    Erscheinen als Value-Signal gesehen wurde."""
    raw = f"{home}|{away}|{commence_time}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _is_prematch(commence_time):
    """True nur, wenn der Anstoss noch in der Zukunft liegt. The Odds API
    mischt bei manchen Sportarten (v.a. Tennis) Live-Quoten in denselben
    Endpoint -- erkennbar daran, dass commence_time schon in der
    Vergangenheit liegt. Solche laufenden Spiele soll der Bankroll-Tracker
    NICHT beruecksichtigen (Value-Zahlen waehrend eines laufenden Matches
    sind ausserdem deutlich weniger belastbar als echte Prematch-Odds)."""
    if not commence_time:
        return False
    try:
        commence = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    except ValueError:
        return False
    return commence > datetime.now(timezone.utc)


def load_ledger(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "starting_bankroll": STARTING_BANKROLL,
        "current_bankroll": STARTING_BANKROLL,
        "bets": [],
    }


def save_ledger(path, ledger):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)


def record_new_bets(ledger, matches, sport_key_field="sport_key"):
    """Durchlaeuft die Match-Liste aus einem results*.json, traegt jedes
    qualifizierende, noch nicht bekannte Value-Signal als neue 'pending'
    Wette ins Ledger ein. Gibt die Anzahl neu hinzugefuegter Wetten zurueck.

    Regeln:
    - nur Prematch (commence_time noch in der Zukunft) -- laufende Spiele
      werden ignoriert, auch wenn sie gerade Value zeigen
    - nur EV > EV_THRESHOLD_PCT
    - nur Quote >= MIN_ODD (aktuell 1.4) -- auch bei Value wird bei sehr
      niedrigen Quoten NICHT gesetzt (zu wenig Ertrag fuer das Risiko,
      und kleine Modellfehler wiegen bei knappen Favoriten-Quoten prozentual
      staerker)
    - maximal EINE Wette pro Spiel insgesamt (siehe _bet_id), unabhaengig
      davon, ob sich der Value-Pick zwischen zwei Laeufen aendert
    - laeuft der Workflow 2x/Tag, wird ein Spiel, das im Morgenlauf schon
      geloggt wurde, im Abendlauf uebersprungen, selbst wenn dort ein
      anderer Ausgang die bessere EV zeigt
    """
    known_ids = {b["id"] for b in ledger["bets"]}
    added = 0

    for m in matches:
        if not m.get("is_value_match"):
            continue
        if m.get("best_ev_pct", 0) <= EV_THRESHOLD_PCT:
            continue
        if not _is_prematch(m.get("commence_time")):
            continue  # laeuft schon / Anstosszeit unbekannt -> nicht beruecksichtigen

        bet_id = _bet_id(m["home"], m["away"], m.get("commence_time"))
        if bet_id in known_ids:
            continue  # dieses SPIEL wurde schon geloggt (unabhaengig vom Tipp)

        # Zugehoerige Outcome-Zeile fuer Kelly/Quote finden
        outcome = next((o for o in m["outcomes"] if o["label"] == m["best_outcome"]), None)
        if outcome is None or outcome["kelly_pct"] <= 0:
            continue
        if outcome["odd"] < MIN_ODD:
            continue  # Value vorhanden, aber Quote zu niedrig -> nicht setzen

        stake = ledger["current_bankroll"] * (outcome["kelly_pct"] / 100.0)
        stake = max(0.0, min(stake, ledger["current_bankroll"]))  # nie mehr als vorhanden
        stake = round(stake, 2)

        ledger["bets"].append({
            "id": bet_id,
            "placed_at": datetime.now(timezone.utc).isoformat(),
            "home": m["home"],
            "away": m["away"],
            "league": m.get("league"),
            "sport_key": m.get(sport_key_field),
            "commence_time": m.get("commence_time"),
            "outcome": m["best_outcome"],
            "odd": outcome["odd"],
            "ev_pct": outcome["ev_pct"],
            "kelly_pct": outcome["kelly_pct"],
            "stake": stake,
            "status": "pending",   # pending | won | lost | void
            "settled_at": None,
            "payout": None,
            "bankroll_after": None,
        })

        # WICHTIG: Der Einsatz wird SOFORT von der verfuegbaren Bankroll
        # abgezogen (wie bei einem echten Kontostand), nicht erst bei der
        # Abrechnung. So sieht man live, wie viel Geld gerade gebunden ist,
        # und ein zweites Signal im selben Lauf staked korrekt gegen das,
        # was nach dem ersten Einsatz tatsaechlich noch uebrig ist.
        ledger["current_bankroll"] = round(ledger["current_bankroll"] - stake, 2)

        added += 1

    return added
