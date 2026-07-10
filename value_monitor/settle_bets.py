#!/usr/bin/env python3
"""settle_bets.py — Prueft alle drei Bankroll-Ledger (WM, Klubs, Tennis) auf
Wetten, deren Spiel inzwischen vorbei sein muesste, und rechnet sie ab.

ZWEI ERGEBNISQUELLEN, je nach Sportart:
- FUSSBALL (WM + Klubs): Scores-Endpoint von The Odds API (wie bisher).
- TENNIS: Ergebnisse von TennisMyLife (stats.tennismylife.org) -- dieselbe
  Quelle wie fuers Elo-Training. Grund: The Odds API dokumentiert fuer
  Tennis nur Quoten, der Scores-Endpoint liefert dort nichts Brauchbares,
  wodurch Tennis-Wetten nie abgerechnet wurden. TML aktualisiert laufende
  Turniere (z.B. Wimbledon) in Echtzeit und enthaelt winner/loser pro Match.

BANKROLL-SEMANTIK: current_bankroll ist der Live-Kontostand. Der Einsatz
wurde beim Platzieren der Wette bereits abgezogen (siehe bankroll.py) --
hier wird bei Gewinn der volle Payout gutgeschrieben, bei Verlust bleibt
er einfach weg, bei Stornierung (void) wird der Einsatz zurueckerstattet.

ZEITFENSTER:
- Fussball: The Odds API liefert Endergebnisse nur bis zu 3 Tage
  rueckwirkend -- danach wird eine unabgerechnete Wette storniert (void).
- Tennis: TML hat keine solche Grenze; Fenster grosszuegiger (7 Tage),
  bevor eine nicht auffindbare Wette storniert wird (z.B. Walkover, der
  nie als Match in der DB auftaucht).

Start:
    python settle_bets.py
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
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bankroll  # noqa: E402

API_KEY = os.environ.get("ODDS_API_KEY", "")
SCORES_URL_TEMPLATE = "https://api.the-odds-api.com/v4/sports/{sport}/scores"
TML_FILES_API = "https://stats.tennismylife.org/api/data-files"

LEDGERS = ["ledger_wm.json", "ledger_clubs.json", "ledger_tennis.json"]

# Erst abrechnen, wenn seit Anstoss genug Zeit fuer ein komplettes Spiel
# vergangen ist (Fussball ~2h, Tennis kann bei Best-of-5 laenger dauern).
SETTLEMENT_BUFFER_HOURS = 4

# Nach so vielen Tagen ohne auffindbares Ergebnis wird eine Wette storniert.
SOCCER_VOID_AFTER_DAYS = bankroll.MAX_SETTLEMENT_WINDOW_DAYS  # 3 (API-Grenze)
TENNIS_VOID_AFTER_DAYS = 7


# ---------------------- Fussball: The Odds API Scores ----------------------

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
    for s in scores:
        if s.get("home_team") == home and s.get("away_team") == away:
            return s
        if s.get("home_team") == away and s.get("away_team") == home:
            return s
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


# ---------------------- Tennis: TennisMyLife-Ergebnisse ----------------------

_TENNIS_RESULTS = None  # Cache, damit die CSVs nur einmal pro Lauf geladen werden


def _fetch_json(url, retries=3, timeout=20):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "value-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * attempt)
    raise RuntimeError(f"{url} nicht erreichbar: {last}")


def _fetch_csv(url, retries=3, timeout=30):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "value-monitor/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(2 * attempt)
    print(f"  Konnte {url} nicht laden: {last}", file=sys.stderr)
    return None


def fetch_tennis_results():
    """Laedt gespielte ATP-Matches des aktuellen Jahres PLUS laufender
    Turniere von TennisMyLife. Gibt Liste von dicts zurueck:
    {winner, loser, tourney_date} (tourney_date im Sackmann-Format YYYYMMDD)."""
    global _TENNIS_RESULTS
    if _TENNIS_RESULTS is not None:
        return _TENNIS_RESULTS

    current_year = str(datetime.now(timezone.utc).year)
    index = _fetch_json(TML_FILES_API)
    files = index.get("files", [])

    # Jahres-Datei ("2026.csv") + alles mit "ongoing" im Namen (laufende
    # Turniere wie Wimbledon stehen dort, bevor sie ins Jahres-File wandern).
    wanted = [
        f for f in files
        if f.get("name", "").replace(".csv", "") == current_year
        or "ongoing" in f.get("name", "").lower()
    ]
    print(f"  TML-Ergebnisdateien: {[f['name'] for f in wanted]}")

    results = []
    for f in wanted:
        text = _fetch_csv(f["url"])
        if text is None:
            continue
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            w, l = row.get("winner_name"), row.get("loser_name")
            if not w or not l:
                continue
            results.append({
                "winner": w,
                "loser": l,
                "tourney_date": row.get("tourney_date", ""),
            })
            count += 1
        print(f"    {f['name']}: {count} Matches")

    _TENNIS_RESULTS = results
    return results


def _resolve_name(raw_name, known_names):
    if raw_name in known_names:
        return raw_name
    close = difflib.get_close_matches(raw_name, known_names, n=1, cutoff=0.85)
    return close[0] if close else None


def find_tennis_result(results, player_a, player_b, commence_time):
    """Sucht das Match zwischen den beiden Spielern, dessen Turnier zeitlich
    zur Wette passt (Turnierstart hoechstens 30 Tage vor Anstoss -- deckt
    auch 2-woechige Grand Slams ab -- und nicht nach dem Anstoss+2 Tage).
    Gibt (winner_name, loser_name) oder None zurueck."""
    try:
        commence = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None

    all_names = list({r["winner"] for r in results} | {r["loser"] for r in results})
    a = _resolve_name(player_a, all_names)
    b = _resolve_name(player_b, all_names)
    if not a or not b:
        return None

    window_start = (commence - timedelta(days=30)).strftime("%Y%m%d")
    window_end = (commence + timedelta(days=2)).strftime("%Y%m%d")

    candidates = [
        r for r in results
        if {r["winner"], r["loser"]} == {a, b}
        and window_start <= r["tourney_date"] <= window_end
    ]
    if not candidates:
        return None
    # Bei mehreren Treffern (sehr selten): das mit dem spaetesten Turnierstart
    best = max(candidates, key=lambda r: r["tourney_date"])
    return best["winner"], best["loser"]


# ---------------------------- Abrechnung ----------------------------

def _apply_win(ledger, b, now):
    payout = round(b["stake"] * b["odd"], 2)
    ledger["current_bankroll"] = round(ledger["current_bankroll"] + payout, 2)
    b["status"] = "won"
    b["settled_at"] = now.isoformat()
    b["payout"] = payout
    b["bankroll_after"] = ledger["current_bankroll"]


def _apply_loss(ledger, b, now):
    b["status"] = "lost"
    b["settled_at"] = now.isoformat()
    b["payout"] = 0.0
    b["bankroll_after"] = ledger["current_bankroll"]


def _apply_void(ledger, b, now, reason):
    ledger["current_bankroll"] = round(ledger["current_bankroll"] + b["stake"], 2)
    b["status"] = "void"
    b["settled_at"] = now.isoformat()
    b["payout"] = b["stake"]
    b["bankroll_after"] = ledger["current_bankroll"]
    print(f"    -> storniert ({reason}), Einsatz {b['stake']}€ zurueckerstattet.")


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

    settled_count = 0
    voided_count = 0

    tennis_due = [b for b in due if (b.get("sport_key") or "").startswith("tennis_")]
    soccer_due = [b for b in due if not (b.get("sport_key") or "").startswith("tennis_")]

    # ---- Tennis ueber TennisMyLife ----
    if tennis_due:
        try:
            results = fetch_tennis_results()
        except RuntimeError as e:
            print(f"  TML nicht erreichbar, Tennis-Abrechnung uebersprungen: {e}", file=sys.stderr)
            results = None

        if results is not None:
            for b in tennis_due:
                commence = datetime.fromisoformat(b["commence_time"].replace("Z", "+00:00"))
                age_days = (now - commence).days
                match_label = f"{b['home']} vs {b['away']}"

                found = find_tennis_result(results, b["home"], b["away"], b["commence_time"])
                if found is None:
                    print(f"  UEBERSPRUNGEN: {match_label} -- kein Ergebnis bei TML gefunden "
                          f"(Alter: {age_days} Tage).")
                    if age_days > TENNIS_VOID_AFTER_DAYS:
                        _apply_void(ledger, b, now, f"nach {age_days} Tagen kein Ergebnis auffindbar")
                        voided_count += 1
                    continue

                winner, loser = found
                won = b["outcome"].endswith(winner)
                # Absicherung: der Tipp muss eindeutig einem der beiden zuordenbar sein
                if not won and not b["outcome"].endswith(loser):
                    print(f"  UEBERSPRUNGEN: {match_label} -- Tipp '{b['outcome']}' passt "
                          f"weder auf Sieger '{winner}' noch Verlierer '{loser}'.")
                    continue

                if won:
                    _apply_win(ledger, b, now)
                else:
                    _apply_loss(ledger, b, now)
                settled_count += 1
                print(f"  ABGERECHNET: {match_label} -- Sieger {winner} -> "
                      f"{'GEWONNEN' if won else 'verloren'}.")

    # ---- Fussball ueber The Odds API Scores ----
    if soccer_due:
        sport_keys = sorted({b["sport_key"] for b in soccer_due if b.get("sport_key")})
        scores_by_sport = {}
        for sk in sport_keys:
            print(f"  Hole Scores fuer {sk} ...")
            scores_by_sport[sk] = fetch_scores(sk)
            time.sleep(0.3)

        for b in soccer_due:
            commence = datetime.fromisoformat(b["commence_time"].replace("Z", "+00:00"))
            age_days = (now - commence).days
            match_label = f"{b['home']} vs {b['away']} ({b.get('sport_key')})"

            scores = scores_by_sport.get(b.get("sport_key"), [])
            entry = find_score_entry(scores, b["home"], b["away"])

            if entry is None:
                available = [f"{s.get('home_team')} vs {s.get('away_team')}" for s in scores[:15]]
                print(f"  UEBERSPRUNGEN: {match_label} -- kein Score-Eintrag gefunden "
                      f"({len(scores)} Events von der API).")
                if available:
                    print(f"    Events der API: {available}")
            elif not entry.get("completed"):
                print(f"  UEBERSPRUNGEN: {match_label} -- Event gefunden, aber noch nicht "
                      f"als beendet markiert (completed={entry.get('completed')}).")

            if entry is None or not entry.get("completed"):
                if age_days > SOCCER_VOID_AFTER_DAYS:
                    _apply_void(ledger, b, now, f"ausserhalb des {SOCCER_VOID_AFTER_DAYS}-Tage-Fensters")
                    voided_count += 1
                continue

            winner = determine_winner(entry, b["home"], b["away"])
            if winner is None:
                print(f"  UEBERSPRUNGEN: {match_label} -- Score nicht auswertbar: {entry.get('scores')}")
                continue

            won = (
                (winner == "home" and b["outcome"].endswith(b["home"])) or
                (winner == "away" and b["outcome"].endswith(b["away"])) or
                (winner == "draw" and b["outcome"] == "Remis")
            )
            if won:
                _apply_win(ledger, b, now)
            else:
                _apply_loss(ledger, b, now)
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
            print(f"  {settled} Wette(n) abgerechnet, {voided} storniert.")
        else:
            print("  keine faelligen Wetten / nichts abrechenbar.")

    print(f"\nGesamt: {total_settled} abgerechnet, {total_voided} storniert.")


if __name__ == "__main__":
    main()
