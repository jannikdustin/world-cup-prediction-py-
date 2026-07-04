#!/usr/bin/env python3
"""fetch_odds_tennis.py — Holt 1X2(2-Weg)-Quoten fuer alle GERADE LAUFENDEN
Tennis-Turniere (ATP + WTA) von The Odds API.

Anders als bei Fussball hat Tennis bei The Odds API keine festen Liga-Keys,
sondern pro Turnier einen eigenen, nur waehrend des Turniers aktiven Key
(z.B. "tennis_atp_wimbledon"). Deshalb wird hier zuerst /v4/sports abgefragt,
um herauszufinden, welche Tennis-Keys GERADE aktiv sind, und erst dann fuer
genau diese Odds geholt. Laeuft gerade kein Turnier, liefert das Skript eine
leere odds_tennis.json -- das ist normal, kein Fehler.

Setup:
    export ODDS_API_KEY="dein-key"    (derselbe Key wie bei Fussball)
    python fetch_odds_tennis.py

Ausgabe: odds_tennis.json
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

SPORTS_LIST_URL = "https://api.the-odds-api.com/v4/sports"
ODDS_URL_TEMPLATE = "https://api.the-odds-api.com/v4/sports/{sport}/odds"


def fetch_active_tennis_keys():
    """Fragt /v4/sports ab und gibt alle aktuell aktiven Tennis-Turnier-Keys
    zurueck, z.B. ['tennis_atp_wimbledon', 'tennis_wta_wimbledon']."""
    url = f"{SPORTS_LIST_URL}?apiKey={API_KEY}"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            all_sports = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"HTTP-Fehler {e.code} beim Abrufen der Sportliste: {body}", file=sys.stderr)
        sys.exit(1)

    tennis = [
        s for s in all_sports
        if s.get("key", "").startswith("tennis_") and s.get("active")
    ]
    return tennis


def fetch_odds_for_sport(sport_key):
    url = ODDS_URL_TEMPLATE.format(sport=sport_key) + (
        f"?apiKey={API_KEY}&regions={REGIONS}&markets={MARKET}&oddsFormat={ODDS_FORMAT}"
    )
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            remaining = resp.headers.get("x-requests-remaining", "?")
            return json.loads(resp.read().decode("utf-8")), remaining
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"  HTTP-Fehler {e.code} bei {sport_key}: {body}", file=sys.stderr)
        return [], None


def average_2way(event, tournament_key, tournament_title):
    """Tennis hat kein Remis -> nur 2 Ausgaenge statt 3 wie bei Fussball."""
    player_a = event.get("home_team")
    player_b = event.get("away_team")
    odds_a, odds_b = [], []

    for bookmaker in event.get("bookmakers", []):
        for market in bookmaker.get("markets", []):
            if market.get("key") != MARKET:
                continue
            for outcome in market.get("outcomes", []):
                name = outcome.get("name")
                price = outcome.get("price")
                if name == player_a:
                    odds_a.append(price)
                elif name == player_b:
                    odds_b.append(price)

    if not (odds_a and odds_b):
        return None

    avg = lambda lst: sum(lst) / len(lst)
    return {
        "player_a": player_a,
        "player_b": player_b,
        "tournament_key": tournament_key,
        "tournament": tournament_title,
        "commence_time": event.get("commence_time"),
        "odds": [round(avg(odds_a), 3), round(avg(odds_b), 3)],
        "bookmaker_count": len(odds_a),
    }


def main():
    if not API_KEY:
        print("FEHLER: ODDS_API_KEY nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    active_tennis = fetch_active_tennis_keys()
    print(f"{len(active_tennis)} aktive Tennis-Turniere gefunden: "
          f"{[s['key'] for s in active_tennis]}")

    all_matches = []
    for sport in active_tennis:
        key = sport["key"]
        title = sport.get("title", key)
        print(f"Hole Quoten fuer {title} ({key}) ...")
        events, remaining = fetch_odds_for_sport(key)
        print(f"  {len(events)} Events, Kontingent verbleibend: {remaining}")

        for event in events:
            row = average_2way(event, key, title)
            if row:
                all_matches.append(row)

        time.sleep(0.3)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odds_tennis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_matches, f, ensure_ascii=False, indent=2)

    print(f"\n{len(all_matches)} Matches mit vollstaendigem 2-Weg-Markt gespeichert -> {out_path}")


if __name__ == "__main__":
    main()
