import hashlib
import json
import time
from pathlib import Path

import httpx
import pandas as pd

CACHE_DIR = Path(__file__).parent / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

SCORITO_BASE = "https://cycling.scorito.com"
CLASSICS_GAME_ID = 302

TYPE_MAP = {
    0: "Other",
    1: "GC",
    2: "Climber",
    3: "TT",
    4: "Sprinter",
    5: "Attacker",
    6: "Support",
    7: "Cobbles",
    8: "Hills",
}

QUALITY_MAP = {
    0: "GC",
    1: "Climb",
    2: "TT",
    3: "Sprint",
    4: "Punch",
    5: "Hill",
    6: "Cobbles",
}


def _cache_path(key: str) -> Path:
    h = hashlib.md5(key.encode()).hexdigest()
    return CACHE_DIR / f"{h}.json"


def _get_cached(key: str, max_age_hours: int = 24):
    path = _cache_path(key)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < max_age_hours * 3600:
            return json.loads(path.read_text())
    return None


def _set_cache(key: str, data):
    path = _cache_path(key)
    path.write_text(json.dumps(data, ensure_ascii=False))


def fetch_teams() -> dict[int, str]:
    """Fetch all cycling teams, return {team_id: team_name}."""
    cache_key = "scorito_teams"
    cached = _get_cached(cache_key)
    if cached:
        return {int(k): v for k, v in cached.items()}

    url = f"{SCORITO_BASE}/cycling/v2.0/team"
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    teams = {}
    for team in data.get("Content", []):
        teams[team["Id"]] = team["Name"]

    _set_cache(cache_key, teams)
    return teams


def fetch_riders(game_id: int = CLASSICS_GAME_ID) -> pd.DataFrame:
    """Fetch all riders for a Scorito game, return as DataFrame."""
    cache_key = f"scorito_riders_{game_id}"
    cached = _get_cached(cache_key)

    if cached:
        riders_raw = cached
    else:
        url = f"{SCORITO_BASE}/cyclingteammanager/v2.0/marketrider/{game_id}"
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        riders_raw = data.get("Content", [])
        _set_cache(cache_key, riders_raw)

    teams = fetch_teams()
    rows = []
    for r in riders_raw:
        row = {
            "rider_id": r["RiderId"],
            "market_rider_id": r["MarketRiderId"],
            "first_name": r["FirstName"],
            "last_name": r["LastName"],
            "name": f"{r['FirstName']} {r['LastName']}",
            "name_short": r["NameShort"],
            "team_id": r["TeamId"],
            "team": teams.get(r["TeamId"], "Unknown"),
            "price": r["Price"],
            "price_m": r["Price"] / 1_000_000,
            "type": TYPE_MAP.get(r["Type"], "Unknown"),
        }

        # Parse qualities
        for q_type, q_name in QUALITY_MAP.items():
            row[f"q_{q_name.lower()}"] = 0
        for q in r.get("Qualities", []):
            q_name = QUALITY_MAP.get(q["Type"])
            if q_name:
                row[f"q_{q_name.lower()}"] = q["Value"]

        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values("price", ascending=False).reset_index(drop=True)
    return df


def get_budget(game_id: int = CLASSICS_GAME_ID) -> int:
    """Return the budget for the game. Scorito API doesn't expose this directly,
    so we use the known value for the 2026 Klassiekerspel."""
    return 50_000_000


if __name__ == "__main__":
    df = fetch_riders()
    print(f"Fetched {len(df)} riders")
    print(f"\nTop 10 duurste renners:")
    print(df[["name", "team", "price_m", "type"]].head(10).to_string(index=False))
    print(f"\nPrijsverdeling:")
    print(df["price_m"].value_counts().sort_index(ascending=False))
