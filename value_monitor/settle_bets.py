#!/usr/bin/env python3
"""settle_bets.py — Prueft alle drei Bankroll-Ledger (WM, Klubs, Tennis) auf
Wetten, deren Spiel inzwischen vorbei sein muesste, holt das Endergebnis ueber
den Scores-Endpoint von The Odds API und schreibt Gewinn/Verlust in die
jeweilige Bankroll fort.

BANKROLL-SEMANTIK: current_bankroll ist der Live-Kontostand. Der Einsatz
wurde beim Platzieren der Wette bereits abgezogen (siehe bankroll.py) --
hier wird bei Gewinn der volle Payout gutgeschrieben, bei Verlust bleibt
er einfach weg, bei Stornierung (void) wird der Einsatz zurueckerstattet.

WICHTIG -- Zeitfenster: The Odds API liefert Endergebnisse nur bis zu 3 Tage
rueckwirkend (daysFrom max. 3). Wetten, die laenger als das unbeglichen sind
(z.B. weil der Workflow mal ausgefallen ist oder das Ergebnis dort nie
auftaucht), werden nach Ablauf des Fensters auf "void" gesetzt -- zaehlen
weder als Gewinn noch Verlust, Einsatz wird der Bankroll wieder gutgeschrieben
(so, als waere die Wette nie platziert worden), damit keine Wette fuer immer
in der Schwebe haengt.

Start:
    python settle_bets.py
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bankroll  # noqa: E402

API_KEY = os.environ.get("ODDS_API_KEY", "")
SCORES_URL_TEMPLATE = "https://api.the-odds-api.com/v4/sports/{sport}/scores"

LEDGERS = ["ledger_wm.json", "ledger_clubs.json", "ledger_tennis.json"]

# Erst abrechnen, wenn seit Anstoss genug Zeit fuer ein komplettes Spiel
# vergangen ist (Fussball ~2h, Tennis kann bei Best-of-5 laenger dauern).
SETTLEMENT_BUFFER_HOURS = 4


def fetch_scores(sport_key, days_from=3):
    url = f"{SCORES_URL_TEMPLATE.format(sport=sport_key)}?apiKey={API_KEY}&daysFrom={days_from}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  HTTP-Fehler {e.code} bei Scores fuer {sport_key}: {body}", file=sys.stderr)
        return []
    except urllib.error.URLError as e:
        print(f"  Netzwerkfehler bei Scores fuer {sport_key}: {e}", file=sys.stderr)
        return []


def find_score_entry(scores, home, away):
    """Sucht den passenden Score-Eintrag per Team-/Spielernamen (exakter
    Match reicht meist, da wir dieselben Namen wie beim Odds-Abruf nutzen)."""
    for s in scores:
        if s.get("home_team") == home and s.get("away_team") == away:
            return s
        if s.get("home_team") == away and s.get("away_team") == home:
            return s  # falls Reihenfolge abweicht
    return None


def determine_winner(score_entry, home, away):
    """Gibt 'home', 'away', 'draw' oder None (nicht auswertbar) zurueck."""
    scores = score_entry.get("scores")
    if not scores:
        return None
    by_name = {s["name"]: s.get("score") for s in scores}
    try:
        home_score = float(by_name.get(home))
        away_score = float(by_name.get(away))
    except (TypeError, ValueError):
        return None

    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"


def settle_ledger(ledger_path):
    ledger = bankroll.load_ledger(ledger_path)
    pending = [b for b in ledger["bets"] if b["status"] == "pending"]
    if not pending:
        return 0, 0

    now = datetime.now(timezone.utc)
    due = []
    for b in pending:
        if not b.get("commence_time"):
            continue
        commence = datetime.fromisoformat(b["commence_time"].replace("Z", "+00:00"))
        if now >= commence + timedelta(hours=SETTLEMENT_BUFFER_HOURS):
            due.append(b)

    if not due:
        return 0, 0

    # Scores nur einmal pro betroffenem sport_key abrufen (API-Kosten sparen)
    sport_keys = sorted({b["sport_key"] for b in due if b.get("sport_key")})
    scores_by_sport = {}
    for sk in sport_keys:
        print(f"  Hole Scores fuer {sk} ...")
        scores_by_sport[sk] = fetch_scores(sk)
        time.sleep(0.3)

    settled_count = 0
    voided_count = 0

    for b in due:
        commence = datetime.fromisoformat(b["commence_time"].replace("Z", "+00:00"))
        age_days = (now - commence).days
        match_label = f"{b['home']} vs {b['away']} ({b.get('sport_key')})"

        scores = scores_by_sport.get(b.get("sport_key"), [])
        entry = find_score_entry(scores, b["home"], b["away"])

        if entry is None:
            available = [f"{s.get('home_team')} vs {s.get('away_team')}" for s in scores[:15]]
            print(f"  UEBERSPRUNGEN: {match_label} -- kein Score-Eintrag gefunden "
                  f"({len(scores)} Events insgesamt von der API erhalten). "
                  f"Moeglich: Namensabgleich zwischen Odds- und Scores-Endpoint "
                  f"weicht ab, oder Event fehlt (noch) in der Scores-Antwort.")
            print(f"    Events, die die API tatsaechlich zurueckgegeben hat: {available}")
        elif not entry.get("completed"):
            print(f"  UEBERSPRUNGEN: {match_label} -- Event gefunden, aber "
                  f"'completed' ist noch nicht true (API-Status: "
                  f"completed={entry.get('completed')}, scores={entry.get('scores')}).")

        if entry is None or not entry.get("completed"):
            if age_days > bankroll.MAX_SETTLEMENT_WINDOW_DAYS:
                # Ausserhalb des 3-Tage-Fensters, Ergebnis nicht mehr
                # zuverlaessig abrufbar -- Wette stornieren. Der Einsatz wurde
                # beim Platzieren bereits von current_bankroll abgezogen
                # (siehe bankroll.py), also muss er hier zurueckgebucht werden.
                ledger["current_bankroll"] = round(ledger["current_bankroll"] + b["stake"], 2)
                b["status"] = "void"
                b["settled_at"] = now.isoformat()
                b["payout"] = b["stake"]  # Einsatz zurueckerstattet
                b["bankroll_after"] = ledger["current_bankroll"]
                voided_count += 1
                print(f"    -> nach {age_days} Tagen ausserhalb des Zeitfensters, storniert.")
            continue  # noch nicht faellig / noch nicht completed, naechstes Mal erneut pruefen

        winner = determine_winner(entry, b["home"], b["away"])
        if winner is None:
            print(f"  UEBERSPRUNGEN: {match_label} -- 'completed' ist true, aber "
                  f"Sieger nicht auswertbar. Rohdaten scores-Feld: {entry.get('scores')}")
            continue  # Score-Format nicht auswertbar, spaeter erneut versuchen

        won = (
            (winner == "home" and b["outcome"].endswith(b["home"])) or
            (winner == "away" and b["outcome"].endswith(b["away"])) or
            (winner == "draw" and b["outcome"] == "Remis")
        )

        # Der Einsatz wurde beim Platzieren bereits abgezogen (siehe
        # bankroll.py). Bei Gewinn kommt der komplette Payout (Einsatz x
        # Quote) zurueck; bei Verlust bleibt der Einsatz einfach weg -- es
        # gibt hier nichts mehr abzuziehen.
        if won:
            payout = round(b["stake"] * b["odd"], 2)
            ledger["current_bankroll"] = round(ledger["current_bankroll"] + payout, 2)
        else:
            payout = 0.0

        b["status"] = "won" if won else "lost"
        b["settled_at"] = now.isoformat()
        b["payout"] = payout
        b["bankroll_after"] = ledger["current_bankroll"]
        settled_count += 1

    bankroll.save_ledger(ledger_path, ledger)
    return settled_count, voided_count


def main():
    if not API_KEY:
        print("FEHLER: ODDS_API_KEY nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    total_settled = 0
    total_voided = 0

    for filename in LEDGERS:
        path = os.path.join(HERE, filename)
        print(f"Pruefe {filename} ...")
        settled, voided = settle_ledger(path)
        total_settled += settled
        total_voided += voided
        if settled or voided:
            print(f"  {settled} Wette(n) abgerechnet, {voided} storniert (Zeitfenster abgelaufen).")
        else:
            print("  keine faelligen Wetten.")

    print(f"\nGesamt: {total_settled} abgerechnet, {total_voided} storniert.")


if __name__ == "__main__":
    main()
