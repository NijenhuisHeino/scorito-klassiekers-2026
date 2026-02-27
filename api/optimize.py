"""API: Optimize team selection."""

import json
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

from pcs_scraper import load_enriched_data, RACE_DISPLAY_NAMES, KOPMAN_MULTIPLIERS
from optimizer import (
    enrich_with_scores,
    optimize_team,
    calculate_kopman_strategy,
    get_team_summary,
    DEFAULT_BUDGET,
)

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

        # Parse query params
        query = parse_qs(urlparse(self.path).query)
        budget = int(query.get("budget", [str(DEFAULT_BUDGET)])[0])
        locked_in = [int(x) for x in query.get("locked_in", [""])[0].split(",") if x]
        locked_out = [int(x) for x in query.get("locked_out", [""])[0].split(",") if x]

        # Run optimizer
        team = optimize_team(df, budget=budget, locked_in=locked_in or None, locked_out=locked_out or None)
        strategy = calculate_kopman_strategy(team)
        summary = get_team_summary(team, strategy)

        # Build response
        team_list = []
        for _, r in team.iterrows():
            team_list.append({
                "id": int(r["market_rider_id"]),
                "name": r["name"],
                "team": r["team"],
                "price": int(r["price"]),
                "priceM": float(r["price_m"]),
                "type": r["type"],
                "numRaces": int(r["num_races"]),
                "expTotal": round(float(r["exp_total"]), 1),
                "valueScore": round(float(r["value_score"]), 1),
                "qualities": {
                    "sprint": int(r["q_sprint"]),
                    "punch": int(r["q_punch"]),
                    "hill": int(r["q_hill"]),
                    "cobbles": int(r["q_cobbles"]),
                },
            })

        # Kopman strategy
        kopman_data = {}
        for race, riders in strategy.items():
            kopman_data[race] = {
                "displayName": RACE_DISPLAY_NAMES.get(race, race),
                "riders": [
                    {
                        "rank": r["rank"],
                        "name": r["name"],
                        "id": int(r["market_rider_id"]),
                        "multiplier": r["multiplier"],
                        "basePoints": round(r["base_points"], 1),
                        "boostedPoints": round(r["boosted_points"], 1),
                    }
                    for r in riders
                ],
            }

        body = json.dumps({
            "team": team_list,
            "strategy": kopman_data,
            "summary": {
                "teamSize": summary["team_size"],
                "totalCostM": round(summary["total_cost_m"], 2),
                "budgetRemainingM": round(summary["budget_remaining_m"], 2),
                "expPointsBase": round(summary["exp_points_without_kopman"], 0),
                "expPointsWithKopman": round(summary["exp_points_with_kopman"], 0),
                "kopmanBonus": round(summary["kopman_bonus"], 0),
                "avgRacesPerRider": round(summary["avg_races_per_rider"], 1),
                "typeDistribution": summary["type_distribution"],
            },
        })

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())
