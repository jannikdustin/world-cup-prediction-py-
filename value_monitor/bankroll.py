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
    """Stabile ID pro Spiel -- nur noch als Referenz/Anzeige im Ledger.
    Die Dopplungs-Erkennung laeuft NICHT mehr ueber diese ID (siehe
    _same_match_exists), weil sich Anstosszeiten bei Tennis auch ueber
    Tagesgrenzen verschieben koennen (z.B. Halbfinale von Do auf Fr wegen
    Regen) und jede zeitbasierte ID dann eine neue Wette vortaeuscht."""
    date_only = (commence_time or "unbekannt")[:10]
    raw = f"{home}|{away}|{date_only}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


DEDUPE_WINDOW_DAYS = 3


def _same_match_exists(ledger, home, away, commence_time):
    """True, wenn im Ledger bereits eine Wette auf dieselbe Paarung liegt,
    deren Anstosszeit hoechstens DEDUPE_WINDOW_DAYS entfernt ist. Faengt
    damit sowohl Uhrzeit-Verschiebungen am selben Tag als auch
    Verschiebungen ueber die Tagesgrenze (Regen, Zeitplanaenderung) ab.
    Dieselben zwei Kontrahenten treffen im Profisport praktisch nie zweimal
    innerhalb von 3 Tagen aufeinander -- eine echte Neuauflage (anderes
    Turnier, Rueckspiel Wochen spaeter) liegt immer ausserhalb des Fensters
    und wird weiterhin als neues Spiel erkannt."""
    try:
        new_dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return False
    for b in ledger["bets"]:
        if b["home"] == home and b["away"] == away and b.get("commence_time"):
            try:
                old_dt = datetime.fromisoformat(b["commence_time"].replace("Z", "+00:00"))
            except ValueError:
                continue
            if abs((new_dt - old_dt).total_seconds()) <= DEDUPE_WINDOW_DAYS * 86400:
                return True
    return False


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
    - maximal EINE Wette pro Spiel insgesamt: dieselbe Paarung mit
      Anstosszeit innerhalb von DEDUPE_WINDOW_DAYS (3 Tage) gilt als
      dasselbe Spiel, auch wenn die Zeit sich verschiebt (siehe
      _same_match_exists), unabhaengig
      davon, ob sich der Value-Pick zwischen zwei Laeufen aendert
    - laeuft der Workflow 2x/Tag, wird ein Spiel, das im Morgenlauf schon
      geloggt wurde, im Abendlauf uebersprungen, selbst wenn dort ein
      anderer Ausgang die bessere EV zeigt
    """
    # WICHTIG: Die Dopplungs-Erkennung laeuft ueber _same_match_exists
    # (Paarung + Anstosszeit innerhalb von DEDUPE_WINDOW_DAYS), NICHT ueber
    # gespeicherte IDs. IDs haben sich als fragil erwiesen: Formelwechsel
    # entwertete Alt-Eintraege, und Tagesgrenzen-Verschiebungen (Tennis,
    # Regen) erzeugten trotzdem Dopplungen.
    added = 0

    for m in matches:
        if not m.get("is_value_match"):
            continue
        if m.get("best_ev_pct", 0) <= EV_THRESHOLD_PCT:
            continue
        if not _is_prematch(m.get("commence_time")):
            continue  # laeuft schon / Anstosszeit unbekannt -> nicht beruecksichtigen

        if _same_match_exists(ledger, m["home"], m["away"], m.get("commence_time")):
            continue  # dieses SPIEL wurde schon bestaked (ggf. mit verschobener Zeit)

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
            "id": _bet_id(m["home"], m["away"], m.get("commence_time")),
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
