"""API: Get all riders with scores."""

import json
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pcs_scraper import load_enriched_data, RACE_DISPLAY_NAMES, RACE_QUALITY_MAP
from optimizer import enrich_with_scores

_cache = {}


def get_riders():
    if "riders" not in _cache:
        df = load_enriched_data()
        df = enrich_with_scores(df)
        _cache["riders"] = df
    return _cache["riders"]


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        df = get_riders()

        # Build JSON response
        riders = []
        for _, r in df.iterrows():
            rider = {
                "id": int(r["market_rider_id"]),
                "name": r["name"],
                "firstName": r["first_name"],
                "lastName": r["last_name"],
                "team": r["team"],
                "price": int(r["price"]),
                "priceM": float(r["price_m"]),
                "type": r["type"],
                "numRaces": int(r["num_races"]),
                "qualities": {
                    "gc": int(r["q_gc"]),
                    "climb": int(r["q_climb"]),
                    "tt": int(r["q_tt"]),
                    "sprint": int(r["q_sprint"]),
                    "punch": int(r["q_punch"]),
                    "hill": int(r["q_hill"]),
                    "cobbles": int(r["q_cobbles"]),
                },
                "expTotal": round(float(r["exp_total"]), 1),
                "valueScore": round(float(r["value_score"]), 1),
                "races": {},
            }

            for race in RACE_DISPLAY_NAMES:
                rider["races"][race] = bool(r.get(f"race_{race}", False))
                rider[f"exp_{race}"] = round(float(r.get(f"exp_{race}", 0)), 1)

            riders.append(rider)

        body = json.dumps({
            "riders": riders,
            "raceNames": RACE_DISPLAY_NAMES,
            "raceQualities": {k: {kk: vv for kk, vv in v.items()} for k, v in RACE_QUALITY_MAP.items()},
            "totalRiders": len(riders),
        })

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "s-maxage=3600")
        self.end_headers()
        self.wfile.write(body.encode())
