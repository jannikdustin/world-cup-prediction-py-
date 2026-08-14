#!/usr/bin/env python3
"""fetch_odds_clubs.py — Holt 1X2-Quoten fuer Top-5-Ligen + europaeische
Klub-Wettbewerbe von The Odds API.

Nutzt denselben ODDS_API_KEY wie fetch_odds.py (WM-Pipeline). Kein
zusaetzlicher Key noetig, nur mehr Requests aus demselben Kontingent
(500/Monat im Free-Tier).

Setup:
    export ODDS_API_KEY="dein-key"
    python fetch_odds_clubs.py

Ausgabe: odds_clubs.json, gleiche Struktur wie odds.json, zusaetzlich
mit "league"-Feld zur Einordnung im Dashboard.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get("ODDS_API_KEY", "")
MARKET = "h2h"
ODDS_FORMAT = "decimal"
REGIONS = "eu,uk"

# Top-5-Ligen + relevante europaeische Wettbewerbe.
# Sport-Keys entsprechen exakt der The-Odds-API-Nomenklatur (Stand 2026).
LEAGUES = {
    "soccer_epl": "Premier League",
    "soccer_spain_la_liga": "La Liga",
    "soccer_italy_serie_a": "Serie A",
    "soccer_germany_bundesliga": "Bundesliga",
    "soccer_germany_bundesliga2": "2. Bundesliga",
    "soccer_france_ligue_one": "Ligue 1",
    "soccer_uefa_champs_league": "Champions League",
    "soccer_uefa_europa_league": "Europa League",
}

BASE_URL = "https://api.the-odds-api.com/v4/sports/{sport}/odds"


def fetch_league(sport_key):
    params = (
        f"?apiKey={API_KEY}"
        f"&regions={REGIONS}"
        f"&markets={MARKET}"
        f"&oddsFormat={ODDS_FORMAT}"
    )
    url = BASE_URL.format(sport=sport_key) + params
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            remaining = resp.headers.get("x-requests-remaining", "?")
            data = json.loads(resp.read().decode("utf-8"))
            return data, remaining
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  HTTP-Fehler {e.code} bei {sport_key}: {body}", file=sys.stderr)
        return [], None
    except urllib.error.URLError as e:
        print(f"  Netzwerkfehler bei {sport_key}: {e}", file=sys.stderr)
        return [], None


def average_1x2(event, sport_key, league_name):
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
        return None

    avg = lambda lst: sum(lst) / len(lst)
    return {
        "home": home_team,
        "sport_key": sport_key,
        "away": away_team,
        "league": league_name,
        "commence_time": event.get("commence_time"),
        "odds": [round(avg(home_odds), 3), round(avg(draw_odds), 3), round(avg(away_odds), 3)],
        "bookmaker_count": len(home_odds),
    }


def main():
    if not API_KEY:
        print("FEHLER: ODDS_API_KEY nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    all_matches = []
    for sport_key, league_name in LEAGUES.items():
        print(f"Hole {league_name} ({sport_key}) ...")
        events, remaining = fetch_league(sport_key)
        print(f"  {len(events)} Events, Kontingent verbleibend: {remaining}")

        for event in events:
            row = average_1x2(event, sport_key, league_name)
            if row:
                all_matches.append(row)

        time.sleep(0.3)  # kleine Pause zwischen Ligen, freundlich zur API

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds_clubs.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, ensure_ascii=False, indent=2)

    print(f"\n{len(all_matches)} Spiele mit vollstaendigem 1X2-Markt gespeichert -> {out_path}")


if __name__ == "__main__":
    main()
