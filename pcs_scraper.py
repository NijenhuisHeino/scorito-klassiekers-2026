"""Race data module - loads enriched rider/race data from jvdlaar/scorito Excel export."""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
EXCEL_PATH = DATA_DIR / "classics-2026.xlsx"

# Column name in Excel -> internal short name
RACE_COLUMNS = {
    "Omloop Nieuwsblad": "omloop",
    "Kuurne - Brussel - Kuurne": "kuurne",
    "Paris-Nice": "paris-nice",
    "Tirreno-Adriatico": "tirreno",
    "Strade Bianche": "strade-bianche",
    "Milano-Sanremo": "milano-sanremo",
    "Ronde Van Brugge - Tour of Bruges": "brugge",
    "E3 Saxo Classic": "e3",
    "In Flanders Fields - From Middelkerke to Wevelgem": "gent-wevelgem",
    "Dwars door Vlaanderen - A travers la Flandre": "dwars",
    "Ronde van Vlaanderen": "ronde-van-vlaanderen",
    "Scheldeprijs": "scheldeprijs",
    "Paris-Roubaix Hauts-de-France": "paris-roubaix",
    "De Brabantse Pijl - La Flèche Brabançonne": "brabantse-pijl",
    "Amstel Gold Race": "amstel",
    "La Flèche Wallonne": "fleche-wallonne",
    "Liège-Bastogne-Liège": "luik",
}

# Friendly display names
RACE_DISPLAY_NAMES = {
    "omloop": "Omloop Het Nieuwsblad",
    "kuurne": "Kuurne-Brussel-Kuurne",
    "paris-nice": "Paris-Nice",
    "tirreno": "Tirreno-Adriatico",
    "strade-bianche": "Strade Bianche",
    "milano-sanremo": "Milano-Sanremo",
    "brugge": "Ronde van Brugge",
    "e3": "E3 Saxo Classic",
    "gent-wevelgem": "Gent-Wevelgem",
    "dwars": "Dwars door Vlaanderen",
    "ronde-van-vlaanderen": "Ronde van Vlaanderen",
    "scheldeprijs": "Scheldeprijs",
    "paris-roubaix": "Paris-Roubaix",
    "brabantse-pijl": "Brabantse Pijl",
    "amstel": "Amstel Gold Race",
    "fleche-wallonne": "Waalse Pijl",
    "luik": "Luik-Bastenaken-Luik",
}

# Race type mapping: which Scorito quality matters most for each race
RACE_QUALITY_MAP = {
    "omloop": {"primary": "cobbles", "secondary": "hill", "weight": 0.7},
    "kuurne": {"primary": "sprint", "secondary": "cobbles", "weight": 0.6},
    "paris-nice": {"primary": "gc", "secondary": "climb", "weight": 0.3},
    "tirreno": {"primary": "gc", "secondary": "climb", "weight": 0.3},
    "strade-bianche": {"primary": "hill", "secondary": "punch", "weight": 0.7},
    "milano-sanremo": {"primary": "sprint", "secondary": "punch", "weight": 0.6},
    "brugge": {"primary": "sprint", "secondary": "cobbles", "weight": 0.4},
    "e3": {"primary": "cobbles", "secondary": "hill", "weight": 0.7},
    "gent-wevelgem": {"primary": "sprint", "secondary": "cobbles", "weight": 0.6},
    "dwars": {"primary": "cobbles", "secondary": "hill", "weight": 0.6},
    "ronde-van-vlaanderen": {"primary": "cobbles", "secondary": "hill", "weight": 0.9},
    "scheldeprijs": {"primary": "sprint", "secondary": None, "weight": 0.5},
    "paris-roubaix": {"primary": "cobbles", "secondary": None, "weight": 0.9},
    "brabantse-pijl": {"primary": "hill", "secondary": "punch", "weight": 0.5},
    "amstel": {"primary": "hill", "secondary": "punch", "weight": 0.7},
    "fleche-wallonne": {"primary": "punch", "secondary": "climb", "weight": 0.7},
    "luik": {"primary": "punch", "secondary": "climb", "weight": 0.8},
}

# Points awarded per finishing position (Scorito Klassiekerspel)
POINTS_TABLE = {
    1: 50, 2: 44, 3: 40, 4: 36, 5: 34,
    6: 32, 7: 30, 8: 28, 9: 26, 10: 24,
    11: 22, 12: 20, 13: 18, 14: 16, 15: 14,
    16: 12, 17: 10, 18: 8, 19: 4, 20: 2,
}

# Kopman multipliers
KOPMAN_MULTIPLIERS = {1: 3.0, 2: 2.5, 3: 2.0}


def load_enriched_data() -> pd.DataFrame:
    """Load the enriched classics-2026 Excel file and return a clean DataFrame."""
    if not EXCEL_PATH.exists():
        raise FileNotFoundError(
            f"Data file not found: {EXCEL_PATH}\n"
            "Download it from: https://github.com/jvdlaar/scorito/raw/main/classics-2026.xlsx"
        )

    raw = pd.read_excel(EXCEL_PATH)

    # Build clean DataFrame
    rows = []
    for _, r in raw.iterrows():
        row = {
            "market_rider_id": r["MarketRiderId"],
            "first_name": r["FirstName"],
            "last_name": r["LastName"],
            "name": f"{r['FirstName']} {r['LastName']}",
            "name_short": r["NameShort"],
            "price": r["Price"],
            "price_m": r["Price"] / 1_000_000,
            "type": r["Type"],
            "team": r["Team"],
            "q_gc": r["Scorito GC"],
            "q_climb": r["Scorito Climb"],
            "q_tt": r["Scorito Time trial"],
            "q_sprint": r["Scorito Sprint"],
            "q_punch": r["Scorito Punch"],
            "q_hill": r["Scorito Hill"],
            "q_cobbles": r["Scorito Cobbles"],
            "num_races": r["Races"],
        }

        # Add race participation columns
        for excel_col, short_name in RACE_COLUMNS.items():
            row[f"race_{short_name}"] = r.get(excel_col, 0) == 1.0

        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values("price", ascending=False).reset_index(drop=True)
    return df


def get_rider_races(row: pd.Series) -> list[str]:
    """Get list of race short names that a rider participates in."""
    return [
        short_name
        for short_name in RACE_DISPLAY_NAMES
        if row.get(f"race_{short_name}", False)
    ]


def get_quality_score(row: pd.Series, quality: str) -> int:
    """Get a rider's quality score by name."""
    col = f"q_{quality}"
    return row.get(col, 0)


if __name__ == "__main__":
    df = load_enriched_data()
    print(f"Loaded {len(df)} riders")
    print(f"\n17 races configured:")
    for short, display in RACE_DISPLAY_NAMES.items():
        count = df[f"race_{short}"].sum()
        print(f"  {display}: {int(count)} renners")

    print(f"\nTop 15 renners op aantal koersen:")
    top = df.nlargest(15, "num_races")[["name", "team", "price_m", "type", "num_races"]]
    print(top.to_string(index=False))

    print(f"\nRenners met 0 koersen: {len(df[df['num_races'] == 0])}")
    print(f"Renners met >= 10 koersen: {len(df[df['num_races'] >= 10])}")
