#!/usr/bin/env python3
"""fetch_odds.py — Holt aktuelle 1X2-Quoten fuer WM-2026-Spiele von The Odds API.

Benoetigt einen kostenlosen API-Key von https://the-odds-api.com (500 Requests/Monat
im Free-Tier reichen locker fuer 1x taeglichen Abruf).

Setup:
    export ODDS_API_KEY="dein-key"
    python fetch_odds.py

Ausgabe: odds.json im selben Ordner, z.B.:
[
  {
    "home": "Germany",
    "away": "France",
    "commence_time": "2026-07-05T18:00:00Z",
    "odds": [3.20, 3.50, 2.10],   # [Heimsieg, Remis, Auswaertssieg], Bookmaker-Durchschnitt
    "bookmaker_count": 6
  },
  ...
]

Team-Namen werden NICHT umbenannt -- das Matching auf deine WC2026_TEAMS-Liste
passiert erst in run_value_scan.py (dort mit Fuzzy-Matching + manueller Override-Tabelle,
falls die Odds API andere Schreibweisen nutzt, z.B. "USA" vs "United States").
"""

import json
import os
import sys
import urllib.request
import urllib.error

API_KEY = os.environ.get("ODDS_API_KEY", "")
SPORT_KEY = "soccer_fifa_world_cup"   # The Odds API Sport-Key fuer die WM
REGIONS = "eu,uk"                      # welche Buchmacher-Regionen abgefragt werden
MARKET = "h2h"                         # 1X2 / Match Winner Markt
ODDS_FORMAT = "decimal"

BASE_URL = f"https://api.the-odds-api.com/v4/sports/{SPORT_KEY}/odds"


def fetch_raw():
    if not API_KEY:
        print("FEHLER: Umgebungsvariable ODDS_API_KEY ist nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    params = (
        f"?apiKey={API_KEY}"
        f"&regions={REGIONS}"
        f"&markets={MARKET}"
        f"&oddsFormat={ODDS_FORMAT}"
    )
    url = BASE_URL + params

    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            remaining = resp.headers.get("x-requests-remaining", "?")
            used = resp.headers.get("x-requests-used", "?")
            print(f"API-Kontingent: {used} verbraucht, {remaining} verbleibend diesen Monat.")
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTP-Fehler {e.code} von The Odds API: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Netzwerkfehler: {e}", file=sys.stderr)
        sys.exit(1)


def average_1x2(event):
    """Mittelt die 1X2-Quoten ueber alle gemeldeten Buchmacher fuer ein Event."""
    home_team = event.get("home_team")
    away_team = event.get("away_team")

    home_odds, draw_odds, away_odds = [], [], []

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") != MARKET:
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name == home_team:
                    home_odds.append(price)
                elif name == away_team:
                    away_odds.append(price)
                elif name == "Draw":
                    draw_odds.append(price)

    if not (home_odds and draw_odds and away_odds):
        return None  # Markt unvollstaendig gemeldet, Spiel ueberspringen

    avg = lambda lst: sum(lst) / len(lst)
    return {
        "home": home_team,
        "away": away_team,
        "commence_time": event.get("commence_time"),
        "odds": [round(avg(home_odds), 3), round(avg(draw_odds), 3), round(avg(away_odds), 3)],
        "bookmaker_count": len(home_odds),
    }


def main():
    raw_events = fetch_raw()
    print(f"{len(raw_events)} Events von The Odds API erhalten.")

    matches = []
    for event in raw_events:
        row = average_1x2(event)
        if row:
            matches.append(row)
        else:
            print(f"  uebersprungen (unvollstaendiger Markt): "
                  f"{event.get('home_team')} vs {event.get('away_team')}")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    print(f"{len(matches)} Spiele mit vollstaendigem 1X2-Markt gespeichert -> {out_path}")


if __name__ == "__main__":
    main()
