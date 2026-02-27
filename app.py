"""Scorito Voorjaarsklassieken 2026 — Dashboard"""

import streamlit as st
import pandas as pd

from pcs_scraper import (
    load_enriched_data,
    RACE_DISPLAY_NAMES,
    RACE_QUALITY_MAP,
    KOPMAN_MULTIPLIERS,
)
from optimizer import (
    enrich_with_scores,
    optimize_team,
    calculate_kopman_strategy,
    get_team_summary,
    DEFAULT_BUDGET,
)

st.set_page_config(
    page_title="Scorito Klassiekers 2026",
    page_icon="🚴",
    layout="wide",
)


@st.cache_data
def load_data():
    df = load_enriched_data()
    df = enrich_with_scores(df)
    return df


def format_price(price_m):
    return f"€{price_m:.2f}M"


def format_points(pts):
    return f"{pts:.1f}"


# ── Load data ──
df = load_data()

# ── Sidebar ──
st.sidebar.title("Scorito Klassiekers 2026")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigatie",
    ["Rennersoverzicht", "Optimaal Team", "Kopmanstrategie", "Team Builder"],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    f"**{len(df)}** renners | **{len(RACE_DISPLAY_NAMES)}** koersen\n\n"
    f"Budget: **€{DEFAULT_BUDGET / 1_000_000:.0f}M**"
)

# ════════════════════════════════════════════════════════════
# PAGE 1: Rennersoverzicht
# ════════════════════════════════════════════════════════════
if page == "Rennersoverzicht":
    st.title("Rennersoverzicht")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        type_filter = st.multiselect(
            "Type", options=sorted(df["type"].unique()), default=[]
        )
    with col2:
        min_price, max_price = st.slider(
            "Prijs (M)", 0.0, 7.0, (0.0, 7.0), step=0.25
        )
    with col3:
        min_races = st.slider("Min. aantal koersen", 0, 17, 0)
    with col4:
        sort_by = st.selectbox(
            "Sorteer op",
            ["exp_total", "value_score", "price_m", "num_races", "name"],
            format_func=lambda x: {
                "exp_total": "Verwachte punten",
                "value_score": "Waarde (pts/M)",
                "price_m": "Prijs",
                "num_races": "Aantal koersen",
                "name": "Naam",
            }[x],
        )

    # Apply filters
    filtered = df.copy()
    if type_filter:
        filtered = filtered[filtered["type"].isin(type_filter)]
    filtered = filtered[
        (filtered["price_m"] >= min_price)
        & (filtered["price_m"] <= max_price)
        & (filtered["num_races"] >= min_races)
    ]

    ascending = sort_by == "name"
    filtered = filtered.sort_values(sort_by, ascending=ascending)

    st.markdown(f"**{len(filtered)}** renners gevonden")

    # Display table
    display_cols = [
        "name", "team", "price_m", "type", "num_races",
        "q_gc", "q_climb", "q_tt", "q_sprint", "q_punch", "q_hill", "q_cobbles",
        "exp_total", "value_score",
    ]
    display_names = {
        "name": "Naam",
        "team": "Team",
        "price_m": "Prijs (M)",
        "type": "Type",
        "num_races": "Koersen",
        "q_gc": "GC",
        "q_climb": "Climb",
        "q_tt": "TT",
        "q_sprint": "Sprint",
        "q_punch": "Punch",
        "q_hill": "Hill",
        "q_cobbles": "Cobbles",
        "exp_total": "Exp. Punten",
        "value_score": "Waarde",
    }

    st.dataframe(
        filtered[display_cols].rename(columns=display_names),
        use_container_width=True,
        height=600,
        column_config={
            "Prijs (M)": st.column_config.NumberColumn(format="€%.2f"),
            "Exp. Punten": st.column_config.NumberColumn(format="%.1f"),
            "Waarde": st.column_config.NumberColumn(format="%.1f"),
        },
    )

# ════════════════════════════════════════════════════════════
# PAGE 2: Optimaal Team
# ════════════════════════════════════════════════════════════
elif page == "Optimaal Team":
    st.title("Optimaal Team")

    budget = st.slider(
        "Budget", 40_000_000, 55_000_000, DEFAULT_BUDGET, step=500_000,
        format="€%dM",
    )

    if st.button("Optimaliseer Team", type="primary"):
        with st.spinner("Team wordt geoptimaliseerd..."):
            team = optimize_team(df, budget=budget)
            strategy = calculate_kopman_strategy(team)
            summary = get_team_summary(team, strategy)

            st.session_state["opt_team"] = team
            st.session_state["opt_strategy"] = strategy
            st.session_state["opt_summary"] = summary

    if "opt_team" in st.session_state:
        team = st.session_state["opt_team"]
        strategy = st.session_state["opt_strategy"]
        summary = st.session_state["opt_summary"]

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Budget gebruikt", f"€{summary['total_cost_m']:.1f}M",
                     f"€{summary['budget_remaining_m']:.1f}M over")
        col2.metric("Exp. punten (basis)", f"{summary['exp_points_without_kopman']:.0f}")
        col3.metric("Exp. punten (met kopman)", f"{summary['exp_points_with_kopman']:.0f}",
                     f"+{summary['kopman_bonus']:.0f} bonus")
        col4.metric("Gem. koersen/renner", f"{summary['avg_races_per_rider']:.1f}")

        st.markdown("---")

        # Team table
        st.subheader("Team samenstelling")
        team_display = team[
            ["name", "team", "price_m", "type", "num_races",
             "q_sprint", "q_punch", "q_hill", "q_cobbles", "exp_total", "value_score"]
        ].rename(columns={
            "name": "Naam", "team": "Team", "price_m": "Prijs (M)",
            "type": "Type", "num_races": "Koersen",
            "q_sprint": "Sprint", "q_punch": "Punch",
            "q_hill": "Hill", "q_cobbles": "Cobbles",
            "exp_total": "Exp. Punten", "value_score": "Waarde",
        })

        st.dataframe(
            team_display,
            use_container_width=True,
            column_config={
                "Prijs (M)": st.column_config.NumberColumn(format="€%.2f"),
                "Exp. Punten": st.column_config.NumberColumn(format="%.1f"),
                "Waarde": st.column_config.NumberColumn(format="%.1f"),
            },
        )

        # Type distribution
        st.subheader("Type verdeling")
        type_counts = team["type"].value_counts()
        st.bar_chart(type_counts)

    else:
        st.info("Klik op 'Optimaliseer Team' om het beste team te berekenen.")

# ════════════════════════════════════════════════════════════
# PAGE 3: Kopmanstrategie
# ════════════════════════════════════════════════════════════
elif page == "Kopmanstrategie":
    st.title("Kopmanstrategie")

    if "opt_team" not in st.session_state:
        st.warning("Ga eerst naar 'Optimaal Team' en genereer een team.")
    else:
        team = st.session_state["opt_team"]
        strategy = st.session_state["opt_strategy"]

        st.markdown(
            "Per koers worden de 3 beste renners als kopman aangewezen: "
            "**1e kopman (3x)**, **2e kopman (2.5x)**, **3e kopman (2x)**."
        )

        # Race selector
        selected_race = st.selectbox(
            "Selecteer koers",
            options=[r for r in RACE_DISPLAY_NAMES if strategy.get(r)],
            format_func=lambda x: RACE_DISPLAY_NAMES[x],
        )

        if selected_race and strategy.get(selected_race):
            riders = strategy[selected_race]
            race_info = RACE_QUALITY_MAP.get(selected_race, {})

            col1, col2 = st.columns([2, 1])
            with col2:
                st.markdown("**Koerstype:**")
                st.markdown(f"- Primair: **{race_info.get('primary', '-').title()}**")
                if race_info.get("secondary"):
                    st.markdown(f"- Secundair: **{race_info['secondary'].title()}**")
                st.markdown(f"- Gewicht: **{race_info.get('weight', 0.5)}**")

            with col1:
                # Kopmannen
                for r in riders[:3]:
                    mult_label = f"{r['multiplier']}x"
                    rank_emoji = ["🥇", "🥈", "🥉"][r["rank"] - 1]
                    st.markdown(
                        f"{rank_emoji} **{r['rank']}e Kopman** — "
                        f"**{r['name']}** | "
                        f"{r['base_points']:.1f} pts × {mult_label} = "
                        f"**{r['boosted_points']:.1f} pts**"
                    )

                # Remaining riders
                if len(riders) > 3:
                    st.markdown("---")
                    st.markdown("**Overige renners in deze koers:**")
                    for r in riders[3:]:
                        st.markdown(
                            f"- {r['name']} — {r['base_points']:.1f} pts"
                        )

            # Overview table across all races
            st.markdown("---")
            st.subheader("Overzicht alle koersen")

            overview_rows = []
            total_exp = 0
            for race in RACE_DISPLAY_NAMES:
                race_riders = strategy.get(race, [])
                if not race_riders:
                    continue
                display = RACE_DISPLAY_NAMES[race]
                kopmannen = race_riders[:3]
                race_total = sum(r["boosted_points"] for r in race_riders)
                total_exp += race_total

                kop_names = " | ".join(
                    f"{r['name']} ({r['multiplier']}x)" for r in kopmannen
                )
                overview_rows.append({
                    "Koers": display,
                    "1e Kopman": kopmannen[0]["name"] if len(kopmannen) > 0 else "-",
                    "2e Kopman": kopmannen[1]["name"] if len(kopmannen) > 1 else "-",
                    "3e Kopman": kopmannen[2]["name"] if len(kopmannen) > 2 else "-",
                    "Totaal exp.": race_total,
                })

            overview_df = pd.DataFrame(overview_rows)
            st.dataframe(
                overview_df,
                use_container_width=True,
                column_config={
                    "Totaal exp.": st.column_config.NumberColumn(format="%.1f"),
                },
            )
            st.metric("Totaal verwachte punten (alle koersen)", f"{total_exp:.0f}")

# ════════════════════════════════════════════════════════════
# PAGE 4: Team Builder
# ════════════════════════════════════════════════════════════
elif page == "Team Builder":
    st.title("Team Builder")
    st.markdown("Stel je eigen team samen en vergelijk met het optimale team.")

    # Initialize session state for manual team
    if "manual_team_ids" not in st.session_state:
        st.session_state["manual_team_ids"] = []

    # Search and add riders
    search = st.text_input("Zoek renner (naam)")
    if search:
        matches = df[df["name"].str.contains(search, case=False, na=False)]
        if len(matches) > 0:
            for _, rider in matches.head(10).iterrows():
                rid = rider["market_rider_id"]
                in_team = rid in st.session_state["manual_team_ids"]
                col1, col2, col3, col4, col5 = st.columns([3, 2, 1, 1, 1])
                col1.write(rider["name"])
                col2.write(rider["team"])
                col3.write(format_price(rider["price_m"]))
                col4.write(f"{rider['num_races']} koersen")
                if in_team:
                    if col5.button("Verwijder", key=f"rem_{rid}"):
                        st.session_state["manual_team_ids"].remove(rid)
                        st.rerun()
                else:
                    if col5.button("Toevoegen", key=f"add_{rid}"):
                        st.session_state["manual_team_ids"].append(rid)
                        st.rerun()
        else:
            st.write("Geen renners gevonden.")

    st.markdown("---")

    # Current team
    team_ids = st.session_state["manual_team_ids"]
    manual_team = df[df["market_rider_id"].isin(team_ids)]

    team_cost = manual_team["price"].sum()
    budget_left = DEFAULT_BUDGET - team_cost

    col1, col2, col3 = st.columns(3)
    col1.metric("Renners", f"{len(team_ids)}/20")
    col2.metric("Budget", f"€{team_cost / 1_000_000:.2f}M / €{DEFAULT_BUDGET / 1_000_000:.0f}M")
    col3.metric("Resterend", f"€{budget_left / 1_000_000:.2f}M",
                delta_color="inverse" if budget_left < 0 else "normal")

    if budget_left < 0:
        st.error("Je bent over budget!")

    if len(manual_team) > 0:
        st.subheader(f"Jouw team ({len(manual_team)} renners)")

        display = manual_team[
            ["name", "team", "price_m", "type", "num_races", "exp_total", "value_score"]
        ].rename(columns={
            "name": "Naam", "team": "Team", "price_m": "Prijs (M)",
            "type": "Type", "num_races": "Koersen",
            "exp_total": "Exp. Punten", "value_score": "Waarde",
        })
        st.dataframe(display, use_container_width=True)

        total_exp = manual_team["exp_total"].sum()
        st.metric("Totaal verwachte punten (basis)", f"{total_exp:.0f}")

        # Kopman strategy for manual team
        if len(manual_team) >= 3:
            strategy = calculate_kopman_strategy(manual_team)
            total_with_kop = sum(
                sum(r["boosted_points"] for r in riders)
                for riders in strategy.values()
            )
            st.metric("Totaal verwachte punten (met kopman)", f"{total_with_kop:.0f}")

        # Comparison with optimal
        if "opt_team" in st.session_state:
            st.markdown("---")
            st.subheader("Vergelijking met optimaal team")
            opt_summary = st.session_state["opt_summary"]

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Jouw team:**")
                st.write(f"- Renners: {len(manual_team)}")
                st.write(f"- Budget: €{team_cost / 1_000_000:.2f}M")
                st.write(f"- Exp. punten: {total_exp:.0f}")

            with col2:
                st.markdown("**Optimaal team:**")
                st.write(f"- Renners: {opt_summary['team_size']}")
                st.write(f"- Budget: €{opt_summary['total_cost_m']:.2f}M")
                st.write(f"- Exp. punten: {opt_summary['exp_points_without_kopman']:.0f}")

            diff = total_exp - opt_summary["exp_points_without_kopman"]
            if diff > 0:
                st.success(f"Jouw team scoort {diff:.0f} punten MEER dan het optimale team!")
            elif diff < 0:
                st.warning(f"Jouw team scoort {abs(diff):.0f} punten MINDER dan het optimale team.")
            else:
                st.info("Jouw team scoort gelijk aan het optimale team!")

        # Quick-add optimal team
        if st.button("Laad optimaal team"):
            if "opt_team" in st.session_state:
                st.session_state["manual_team_ids"] = (
                    st.session_state["opt_team"]["market_rider_id"].tolist()
                )
                st.rerun()
            else:
                st.warning("Genereer eerst een optimaal team op de 'Optimaal Team' pagina.")

    # Clear team
    if team_ids and st.button("Wis team", type="secondary"):
        st.session_state["manual_team_ids"] = []
        st.rerun()
