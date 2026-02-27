"""Build script: pre-compute all rider data and scores, export as static JSON."""

import json
from pcs_scraper import load_enriched_data, RACE_DISPLAY_NAMES, RACE_QUALITY_MAP, KOPMAN_MULTIPLIERS, POINTS_TABLE
from optimizer import enrich_with_scores, DEFAULT_BUDGET

def build():
    print("Loading and enriching data...")
    df = load_enriched_data()
    df = enrich_with_scores(df)

    riders = []
    for _, r in df.iterrows():
        rider = {
            "id": int(r["market_rider_id"]),
            "name": r["name"],
            "team": r["team"],
            "price": int(r["price"]),
            "priceM": round(float(r["price_m"]), 2),
            "type": r["type"],
            "numRaces": int(r["num_races"]),
            "q": {
                "gc": int(r["q_gc"]),
                "climb": int(r["q_climb"]),
                "tt": int(r["q_tt"]),
                "sprint": int(r["q_sprint"]),
                "punch": int(r["q_punch"]),
                "hill": int(r["q_hill"]),
                "cobbles": int(r["q_cobbles"]),
            },
            "expTotal": round(float(r["exp_total"]), 1),
            "value": round(float(r["value_score"]), 1),
            "races": {},
            "exp": {},
        }

        for race in RACE_DISPLAY_NAMES:
            rider["races"][race] = bool(r.get(f"race_{race}", False))
            rider["exp"][race] = round(float(r.get(f"exp_{race}", 0)), 1)

        riders.append(rider)

    data = {
        "riders": riders,
        "raceNames": RACE_DISPLAY_NAMES,
        "raceQualities": RACE_QUALITY_MAP,
        "kopmanMultipliers": {str(k): v for k, v in KOPMAN_MULTIPLIERS.items()},
        "pointsTable": {str(k): v for k, v in POINTS_TABLE.items()},
        "budget": DEFAULT_BUDGET,
        "totalRiders": len(riders),
    }

    out_path = "public/data.json"
    with open(out_path, "w") as f:
        json.dump(data, f, separators=(",", ":"))

    print(f"Written {out_path} ({len(riders)} riders, {len(json.dumps(data))//1024}KB)")

if __name__ == "__main__":
    build()
