"""Conflict & displacement: battle deaths (UCDP via the World Bank) and forced displacement (UNHCR)."""

import pandas as pd
import streamlit as st

from prm import charts, config, ui

core, year, values, scores = ui.load()
hist = ui.history(core)
table = ui.master_table(core, values, scores, hist)
names = dict(zip(table["iso3"], table["name"]))
known = set(names)

st.title("Conflict & displacement")
st.markdown(
    "Where people are being killed in armed conflict and forced from their homes. Battle deaths follow the "
    "Uppsala Conflict Data Program (state-based conflict, via the World Bank); displacement is UNHCR's count of "
    "refugees, asylum seekers, others in need of international protection and internally displaced people."
)

# --- Data -------------------------------------------------------------------------------------------
bd = core["series"].get("battle_deaths", pd.DataFrame(columns=["iso3", "year", "value"]))
bd = bd[bd["iso3"].isin(known)]
dp = core["series"].get("displaced", pd.DataFrame(columns=["iso3", "year", "value"]))
dp = dp[dp["iso3"].isin(known)]
flows = core.get("flows")
bd_year = int(bd["year"].max()) if len(bd) else None
dp_year = int(dp["year"].max()) if len(dp) else None
latest_bd = bd[bd["year"] == bd_year].set_index("iso3")["value"] if bd_year else pd.Series(dtype=float)
prev_bd = bd[bd["year"] == bd_year - 1].set_index("iso3")["value"] if bd_year else pd.Series(dtype=float)

# --- Headline numbers ----------------------------------------------------------------------------------
deaths_by_year = bd.groupby("year")["value"].sum()
displaced_by_year = dp.groupby("year")["value"].sum()
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Active armed conflicts", int((latest_bd >= 25).sum()), border=True,
          delta=None if prev_bd.empty else int((latest_bd >= 25).sum() - (prev_bd >= 25).sum()), delta_color="inverse",
          help=f"Countries with at least 25 battle-related deaths in {bd_year} (UCDP threshold)")
k2.metric("At war", int((latest_bd >= 1000).sum()), border=True,
          delta=None if prev_bd.empty else int((latest_bd >= 1000).sum() - (prev_bd >= 1000).sum()),
          delta_color="inverse", help=f"At least 1,000 battle-related deaths in {bd_year}")
k3.metric(f"Battle deaths, {bd_year}", f"{latest_bd.sum():,.0f}", border=True,
          chart_data=deaths_by_year[deaths_by_year.index >= 2010].tolist(),
          delta=None if prev_bd.empty else f"{(latest_bd.sum() / prev_bd.sum() - 1):+.0%}" if prev_bd.sum() else None,
          delta_color="inverse")
k4.metric(f"Forcibly displaced, {dp_year}", ui.fmt_population(displaced_by_year.iloc[-1]) if len(displaced_by_year) else "—",
          border=True, chart_data=displaced_by_year.tolist(),
          delta=f"{(displaced_by_year.iloc[-1] / displaced_by_year.iloc[-2] - 1):+.0%}" if len(displaced_by_year) > 1 else None,
          delta_color="inverse", help="People displaced from their country of origin, inside or outside it (UNHCR)")
k5.metric("Refugees across borders", ui.fmt_population(flows["value"].sum()) if flows is not None else "—", border=True,
          help="Refugees, asylum seekers and others in need of protection living outside their country (UNHCR)")

# --- The globe: stability risk, conflict rings, refugee arcs -------------------------------------------------
st.subheader("On the globe")
displaced_now = dp[dp["year"] == dp_year].set_index("iso3")["value"] if dp_year else pd.Series(dtype=float)
notes = {}
for iso3 in known:
    parts = []
    if latest_bd.get(iso3, 0) >= 25:
        parts.append(f"{latest_bd[iso3]:,.0f} battle deaths in {bd_year}")
    if displaced_now.get(iso3, 0) >= 100_000:
        parts.append(f"{ui.fmt_population(displaced_now[iso3])} people displaced ({dp_year})")
    if parts:
        notes[iso3] = " · ".join(parts)
ui.globe_panel(table=table, hist=hist, flows=flows, metric="stability", metric_label="Stability", key="cf_globe",
               notes=notes, layers={"spin": True, "flows": True, "conflict": True},
               hint="Rings = armed conflict · arcs = refugee flows · ▶ replays since " + str(config.HISTORY_START))
st.caption("Countries coloured by the Political Stability & Violence pillar (brighter = riskier). Pulsing rings mark "
           "armed conflict (bigger and faster = more deaths); arcs run from refugees' origin to their host country. "
           "Click a country to see only its flows.")

tab_conflict, tab_displacement = st.tabs(["⚔️ Armed conflict", "🧳 Displacement & refugee flows"])

# --- Armed conflict ------------------------------------------------------------------------------------------
with tab_conflict:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Battle deaths worldwide")
        recent = deaths_by_year[deaths_by_year.index >= 1990]
        st.plotly_chart(charts.yearly_bars(recent.index, recent.values, "Battle-related deaths", charts.WORSE, "deaths"),
                        config={"displayModeBar": False})
        st.caption("Sum over all countries of deaths in state-based armed conflict (UCDP), by the country where they occurred.")
    with c2:
        st.subheader("Deadliest conflicts over time")
        top = latest_bd.nlargest(6).index.tolist()
        st.plotly_chart(charts.compare_lines(core["series"], "battle_deaths", top, names, "Battle-related deaths",
                                             start_year=2010), config={"displayModeBar": False})
        st.caption(f"The six countries with the most battle deaths in {bd_year}.")

    st.subheader(f"Countries in armed conflict ({bd_year})")
    st.caption("At least 25 battle-related deaths in the year. Click a row to open the country.")
    conflict = table[table["iso3"].isin(latest_bd[latest_bd >= 25].index)].copy()
    conflict["deaths"] = conflict["iso3"].map(latest_bd)
    conflict["deaths_prev"] = conflict["iso3"].map(prev_bd).fillna(0)
    conflict["deaths_change"] = conflict["deaths"] - conflict["deaths_prev"]
    conflict = conflict.join(values[["battle_deaths_100k", "displaced_share"]], on="iso3")
    conflict["level"] = conflict["deaths"].map(lambda d: "🔴 War (≥ 1,000)" if d >= 1000 else "🟠 Armed conflict")
    conflict = conflict.sort_values("deaths", ascending=False).reset_index(drop=True)
    event = st.dataframe(
        conflict[["iso3", "flag", "name", "level", "deaths", "deaths_change", "battle_deaths_100k", "displaced_share",
                  "stability", "tier"]],
        hide_index=True, height=460, on_select="rerun", selection_mode="single-row", key="cf_table",
        column_config={
            "iso3": None, "flag": ui.FLAG_COLUMN, "name": "Country", "level": "Level",
            "deaths": st.column_config.NumberColumn(f"Deaths {bd_year}", format="localized"),
            "deaths_change": st.column_config.NumberColumn(f"vs {bd_year - 1}", format="%+d"),
            "battle_deaths_100k": st.column_config.NumberColumn("Per 100k", format="%.2f"),
            "displaced_share": st.column_config.NumberColumn("Displaced (% pop.)", format="%.1f%%"),
            "stability": st.column_config.ProgressColumn("Stability risk", min_value=0, max_value=100, format="%.0f",
                                                         color=config.PILLAR_COLORS["stability"]),
            "tier": "Tier",
        },
    )
    if event and event.selection.rows:
        ui.go_to_country(conflict.iloc[event.selection.rows[0]]["iso3"])

# --- Displacement ----------------------------------------------------------------------------------------------
with tab_displacement:
    d1, d2 = st.columns(2)
    with d1:
        st.subheader("Forcibly displaced people")
        st.plotly_chart(charts.yearly_bars(displaced_by_year.index, displaced_by_year.values, "People",
                                           config.PILLAR_COLORS["social"], "people"), config={"displayModeBar": False})
        st.caption("Refugees, asylum seekers, others in need of protection and internally displaced people, by year (UNHCR).")
    with d2:
        st.subheader(f"Largest displaced populations ({dp_year})")
        origins = dp[dp["year"] == dp_year].nlargest(10, "value").assign(name=lambda d: d["iso3"].map(names))
        event = st.plotly_chart(charts.ranked_bars(origins, "value", "name", charts.WORSE, "people displaced"),
                                config={"displayModeBar": False}, on_select="rerun", selection_mode="points",
                                key="cf_origins")
        if iso3 := ui.clicked_iso3(event):
            ui.go_to_country(iso3)

    if flows is not None and not flows.empty:
        flows_year = int(flows["year"].max())
        h1, h2 = st.columns([1, 1.6])
        with h1:
            st.subheader(f"Largest host countries ({flows_year})")
            hosts = (flows[flows["host"].isin(known)].groupby("host", as_index=False)["value"].sum()
                     .nlargest(10, "value").rename(columns={"host": "iso3"}))
            hosts["name"] = hosts["iso3"].map(names)
            event = st.plotly_chart(charts.ranked_bars(hosts, "value", "name", charts.BETTER, "refugees hosted"),
                                    config={"displayModeBar": False}, on_select="rerun", selection_mode="points",
                                    key="cf_hosts")
            if iso3 := ui.clicked_iso3(event):
                ui.go_to_country(iso3)
        with h2:
            st.subheader("The 25 largest refugee corridors")
            st.plotly_chart(charts.refugee_sankey(flows, names), config={"displayModeBar": False})
            st.caption("Origins (red, left) to host countries (blue, right); band width = people. Hover for numbers. "
                       "Internally displaced people are not included, as they never cross a border.")
    else:
        st.info("Refugee flow data is not available right now.")

ui.footer()
