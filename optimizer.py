"""Team and captain optimization for Scorito Klassiekerspel 2026."""

import pandas as pd
from pulp import LpMaximize, LpProblem, LpVariable, lpSum, PULP_CBC_CMD

from pcs_scraper import (
    RACE_QUALITY_MAP,
    RACE_DISPLAY_NAMES,
    POINTS_TABLE,
    KOPMAN_MULTIPLIERS,
    get_rider_races,
)

# Default budget for 2026 Klassiekerspel
DEFAULT_BUDGET = 50_000_000


def calculate_race_score(row: pd.Series, race: str) -> float:
    """Calculate expected score for a rider in a specific race.

    Based on Scorito quality ratings and race type mapping.
    Returns a score from 0-100 representing expected performance.
    """
    if not row.get(f"race_{race}", False):
        return 0.0

    mapping = RACE_QUALITY_MAP.get(race)
    if not mapping:
        return 0.0

    primary = mapping["primary"]
    secondary = mapping.get("secondary")
    race_weight = mapping.get("weight", 0.5)

    # Get quality scores (0-10 scale)
    primary_score = row.get(f"q_{primary}", 0)
    secondary_score = row.get(f"q_{secondary}", 0) if secondary else 0

    # Weighted combination: 70% primary, 30% secondary
    quality_score = primary_score * 0.7 + secondary_score * 0.3

    # Scale by race importance weight
    return quality_score * race_weight


def calculate_expected_points(row: pd.Series, race: str) -> float:
    """Calculate expected Scorito points for a rider in a specific race.

    Maps quality score to expected finishing position and then to points.
    """
    score = calculate_race_score(row, race)
    if score <= 0:
        return 0.0

    # Map quality score (0-10) to expected points
    # Top quality (score ~7-10) -> likely top 5 finisher
    # Good quality (score ~4-7) -> likely top 10-15
    # Average quality (score ~2-4) -> likely top 15-20
    # Low quality (score ~0-2) -> unlikely to score

    if score >= 7:
        # Top tier: expected around position 1-5
        avg_points = 40.0  # average of top 5 positions
        probability = 0.7
    elif score >= 5:
        # Strong: expected around position 3-10
        avg_points = 30.0
        probability = 0.5
    elif score >= 3:
        # Decent: expected around position 8-15
        avg_points = 20.0
        probability = 0.35
    elif score >= 1.5:
        # Below average but still racing
        avg_points = 10.0
        probability = 0.2
    else:
        # Low quality, just racing
        avg_points = 5.0
        probability = 0.1

    return avg_points * probability


def calculate_total_expected_points(row: pd.Series) -> float:
    """Calculate total expected points for a rider across all races."""
    total = 0.0
    for race in RACE_DISPLAY_NAMES:
        total += calculate_expected_points(row, race)
    return total


def calculate_value_score(row: pd.Series) -> float:
    """Calculate value score (expected points per million spent)."""
    expected = calculate_total_expected_points(row)
    if row["price_m"] > 0:
        return expected / row["price_m"]
    return 0.0


def enrich_with_scores(df: pd.DataFrame) -> pd.DataFrame:
    """Add expected points and value scores to DataFrame."""
    df = df.copy()

    # Per-race expected points
    for race in RACE_DISPLAY_NAMES:
        df[f"exp_{race}"] = df.apply(lambda r: calculate_expected_points(r, race), axis=1)

    # Totals
    exp_cols = [f"exp_{race}" for race in RACE_DISPLAY_NAMES]
    df["exp_total"] = df[exp_cols].sum(axis=1)
    df["value_score"] = df.apply(calculate_value_score, axis=1)

    return df


def optimize_team(
    df: pd.DataFrame,
    budget: int = DEFAULT_BUDGET,
    team_size: int = 20,
    locked_in: list[int] | None = None,
    locked_out: list[int] | None = None,
) -> pd.DataFrame:
    """Find the optimal team using Integer Linear Programming.

    Args:
        df: DataFrame with rider data and expected points
        budget: Maximum budget
        team_size: Number of riders to select
        locked_in: List of market_rider_ids that must be in the team
        locked_out: List of market_rider_ids that must not be in the team

    Returns:
        DataFrame with selected riders
    """
    locked_in = locked_in or []
    locked_out = locked_out or []

    # Ensure we have expected points
    if "exp_total" not in df.columns:
        df = enrich_with_scores(df)

    # Filter out riders with 0 races (they can never score)
    candidates = df[df["num_races"] > 0].copy()

    # Also include locked_in riders even if they have 0 races
    for rid in locked_in:
        if rid not in candidates["market_rider_id"].values:
            locked_rider = df[df["market_rider_id"] == rid]
            candidates = pd.concat([candidates, locked_rider])

    candidates = candidates.reset_index(drop=True)

    # Create ILP problem
    prob = LpProblem("Scorito_Team_Selection", LpMaximize)

    # Decision variables: select[i] = 1 if rider i is in the team
    n = len(candidates)
    select = [LpVariable(f"select_{i}", cat="Binary") for i in range(n)]

    # Objective: maximize total expected points
    prob += lpSum(
        select[i] * candidates.iloc[i]["exp_total"] for i in range(n)
    )

    # Constraint: team size
    prob += lpSum(select[i] for i in range(n)) == team_size

    # Constraint: budget
    prob += lpSum(
        select[i] * candidates.iloc[i]["price"] for i in range(n)
    ) <= budget

    # Constraint: locked in riders
    for rid in locked_in:
        idx = candidates[candidates["market_rider_id"] == rid].index
        if len(idx) > 0:
            prob += select[idx[0]] == 1

    # Constraint: locked out riders
    for rid in locked_out:
        idx = candidates[candidates["market_rider_id"] == rid].index
        if len(idx) > 0:
            prob += select[idx[0]] == 0

    # Solve
    solver = PULP_CBC_CMD(msg=False)
    prob.solve(solver)

    # Extract selected riders
    selected_indices = [i for i in range(n) if select[i].varValue == 1]
    team = candidates.iloc[selected_indices].copy()
    team = team.sort_values("exp_total", ascending=False).reset_index(drop=True)

    return team


def calculate_kopman_strategy(team: pd.DataFrame) -> dict[str, list[dict]]:
    """Determine optimal kopman (captain) strategy per race.

    For each race, select the 3 riders with the highest expected points
    and assign them as 1st/2nd/3rd kopman with their multipliers.

    Returns:
        Dict mapping race short name -> list of {rider, multiplier, base_points, boosted_points}
    """
    strategy = {}

    for race in RACE_DISPLAY_NAMES:
        exp_col = f"exp_{race}"
        if exp_col not in team.columns:
            continue

        # Get riders that participate in this race
        racing = team[team[f"race_{race}"] == True].copy()
        if len(racing) == 0:
            strategy[race] = []
            continue

        # Sort by expected points in this race
        racing = racing.sort_values(exp_col, ascending=False)

        kopmannen = []
        for i, (_, rider) in enumerate(racing.iterrows()):
            if i >= 3:
                break
            rank = i + 1
            multiplier = KOPMAN_MULTIPLIERS[rank]
            base_pts = rider[exp_col]
            kopmannen.append({
                "rank": rank,
                "name": rider["name"],
                "market_rider_id": rider["market_rider_id"],
                "multiplier": multiplier,
                "base_points": base_pts,
                "boosted_points": base_pts * multiplier,
            })

        # Also add remaining riders (no multiplier)
        remaining = []
        for i, (_, rider) in enumerate(racing.iterrows()):
            if i < 3:
                continue
            remaining.append({
                "rank": i + 1,
                "name": rider["name"],
                "market_rider_id": rider["market_rider_id"],
                "multiplier": 1.0,
                "base_points": rider[exp_col],
                "boosted_points": rider[exp_col],
            })

        strategy[race] = kopmannen + remaining

    return strategy


def calculate_team_total_with_kopmannen(
    team: pd.DataFrame, strategy: dict
) -> float:
    """Calculate total expected points including kopman multipliers."""
    total = 0.0

    for race, riders in strategy.items():
        for rider in riders:
            total += rider["boosted_points"]

    return total


def get_team_summary(team: pd.DataFrame, strategy: dict) -> dict:
    """Get a summary of team composition and expected performance."""
    total_with_kopman = calculate_team_total_with_kopmannen(team, strategy)
    total_without = team["exp_total"].sum()

    return {
        "team_size": len(team),
        "total_cost": team["price"].sum(),
        "total_cost_m": team["price_m"].sum(),
        "budget_remaining": DEFAULT_BUDGET - team["price"].sum(),
        "budget_remaining_m": (DEFAULT_BUDGET - team["price"].sum()) / 1_000_000,
        "exp_points_without_kopman": total_without,
        "exp_points_with_kopman": total_with_kopman,
        "kopman_bonus": total_with_kopman - total_without,
        "avg_races_per_rider": team["num_races"].mean(),
        "type_distribution": team["type"].value_counts().to_dict(),
    }


if __name__ == "__main__":
    from pcs_scraper import load_enriched_data

    print("Loading data...")
    df = load_enriched_data()

    print("Enriching with scores...")
    df = enrich_with_scores(df)

    print(f"\nTop 20 op verwachte punten:")
    top = df.nlargest(20, "exp_total")[
        ["name", "team", "price_m", "type", "num_races", "exp_total", "value_score"]
    ]
    print(top.to_string(index=False))

    print(f"\nTop 20 op waarde (punten per M):")
    value = df[df["num_races"] > 0].nlargest(20, "value_score")[
        ["name", "team", "price_m", "type", "num_races", "exp_total", "value_score"]
    ]
    print(value.to_string(index=False))

    print("\nOptimizing team...")
    team = optimize_team(df)

    strategy = calculate_kopman_strategy(team)
    summary = get_team_summary(team, strategy)

    print(f"\n{'='*60}")
    print(f"OPTIMAAL TEAM ({summary['team_size']} renners)")
    print(f"{'='*60}")
    print(f"Budget: €{summary['total_cost_m']:.1f}M / €{DEFAULT_BUDGET/1_000_000:.0f}M "
          f"(€{summary['budget_remaining_m']:.1f}M over)")
    print(f"Verwachte punten (zonder kopman): {summary['exp_points_without_kopman']:.0f}")
    print(f"Verwachte punten (met kopman):    {summary['exp_points_with_kopman']:.0f}")
    print(f"Kopman bonus:                     +{summary['kopman_bonus']:.0f}")
    print(f"\nRenners:")
    for _, r in team.iterrows():
        print(f"  {r['name']:25s} | {r['team']:30s} | €{r['price_m']:.2f}M | "
              f"{r['type']:8s} | {r['num_races']} koersen | {r['exp_total']:.1f} exp pts")

    print(f"\nKopmanstrategie per koers:")
    for race, riders in strategy.items():
        if not riders:
            continue
        display = RACE_DISPLAY_NAMES[race]
        print(f"\n  {display}:")
        for r in riders[:3]:
            print(f"    {r['rank']}e kopman: {r['name']:25s} "
                  f"({r['base_points']:.1f} × {r['multiplier']}x = {r['boosted_points']:.1f})")
