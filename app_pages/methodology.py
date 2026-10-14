"""Methodology: how the index is built, and its limits."""

import pandas as pd
import streamlit as st

from prm import config, ui
from prm.config import INDICATORS, PILLARS, RED_FLAGS, SEVERITY_LABEL, TIERS

st.title("Methodology")
st.markdown(
    """
Seismograph follows the standard recipe for composite indicators set out in the
[OECD/JRC *Handbook on Constructing Composite Indicators*](https://www.oecd.org/en/publications/handbook-on-constructing-composite-indicators-methodology-and-user-guide_9789264043466-en.html):
choose indicators that answer a clear question, **normalise** them to a common scale, **aggregate** them into
pillars and a composite with explicit **weights**, and test how sensitive the result is to those choices.
Every step is shown below so a reader can disagree with a specific choice instead of a black box.
"""
)

st.header("1 · The question")
st.markdown(
    "> *How exposed is this country to political, governance, economic and social shocks that could harm people, "
    "organisations and investments operating there — compared with other countries?*\n\n"
    "Four pillars break that question down:"
)
st.dataframe(
    pd.DataFrame(
        [{"Pillar": p.label, "Question it answers": p.question, "Default weight": f"{p.default_weight}%"} for p in PILLARS]
    ),
    hide_index=True,
)
st.caption(
    "Political stability carries the most weight because it is the core of political risk; social pressure the least "
    "because its indicators are the noisiest. You can change the weights in the sidebar and watch rankings move."
)

st.header("2 · The indicators")
ind_rows = [
    {
        "Pillar": config.PILLAR_BY_KEY[i.pillar].short,
        "Indicator": i.label,
        "Unit": i.unit,
        "Riskier when": "higher" if i.higher_is_riskier else "lower",
        "Scaling": "log scale" if i.norm == "log" else "percentile rank",
        "Source": i.source,
        "Why it is here": i.description,
    }
    for i in INDICATORS
]
st.dataframe(pd.DataFrame(ind_rows), hide_index=True, height=640)
ui.cite("index", "oecd_jrc")
st.markdown(
    f"""
**Timing.** WGI scores are the latest annual release (perception data collected during the previous year).
IMF figures are the **current-year estimate** from the latest World Economic Outlook, which makes the economic
pillar the most forward-looking part of the index. World Bank figures use the most recent year available within
a look-back window (shown in the *Indicators* tab of each profile). Battle deaths use the latest UCDP year;
displacement uses the latest UNHCR annual statistics.

**Sources.** [World Bank WGI]({config.URL_WGI}) (2025 methodology revision:
[technical note]({config.URL_WGI_2025})) · [World Development Indicators]({config.URL_WDI}) ·
[IMF World Economic Outlook]({config.URL_IMF_WEO}) · [UNHCR Refugee Data Finder]({config.URL_UNHCR}) ·
[Uppsala Conflict Data Program]({config.URL_UCDP}) · news from the [GDELT Project]({config.URL_GDELT}).
All are retrieved live through their public APIs.
"""
)

st.header("3 · Normalisation")
st.markdown(
    f"""
Indicators come in different units (percent, deaths, months), so each is converted into a **0–100 risk score**:

* **Percentile rank** (most indicators). The riskiest economy in the sample scores 100, the safest 0, and the
  rest are spread evenly between them. Percentiles are robust to outliers — one country with 200% inflation
  does not squash everyone else — but they discard the *size* of gaps between countries.
* **Log scale** (battle deaths per 100k, displacement share). Most countries have zero conflict deaths, so a
  percentile rank would bunch them together in the middle. Instead the score is `log(1 + x)` divided by the
  value at the {config.LOG_CAP_QUANTILE:.0%} percentile of non-zero cases, capped at 100. Zero means zero, and
  scores rise steeply from the first deaths, then flatten.

Direction is handled at this step: for "lower is riskier" indicators (growth, reserves, governance scores) the
ranking is reversed, so 100 always means *most risk*.
"""
)

st.header("4 · Aggregation and weights")
st.markdown(
    f"""
* **Pillar score** = the simple average of its indicator scores. A pillar needs at least
  {config.PILLAR_MIN_SHARE:.0%} of its indicators; otherwise it is left blank rather than guessed.
* **Composite score** = the weighted average of the pillar scores, with weights rescaled over the pillars that are
  available. A country needs at least {config.COMPOSITE_MIN_PILLARS} of 4 pillars to be ranked.
* **Data coverage** (shown on every profile) is the share of the {len(config.SCORED_INDICATORS)} indicators available.
* An arithmetic mean lets a strength in one pillar offset a weakness in another. That suits a broad screening
  tool; a system focused on crisis risk might prefer a geometric mean, which penalises one very weak pillar more
  (the EU's INFORM Risk Index does this).
"""
)

st.header("5 · Tiers")
st.dataframe(
    pd.DataFrame([{"Tier": t.label, "Composite score": f"{int(t.lower)}–{int(t.lower) + 20 if t.lower < 80 else 100}"} for t in TIERS]),
    hide_index=True,
)
st.caption(
    "Averaging many indicator scores pulls composites toward the middle of the scale, so the outer tiers are "
    "reserved for countries that sit at the extremes on most dimensions at once. ‘Low’ means low *relative to "
    "other countries*, not risk-free."
)

st.header("6 · Red flags")
st.markdown(
    "The composite is relative, so it cannot say whether a situation is bad in absolute terms. Red flags fill that gap "
    "with fixed thresholds drawn from common practice — for example UCDP's 25 battle-death threshold for an active armed "
    "conflict and 1,000 for war, and the 3-months-of-imports rule of thumb for reserve adequacy."
)
st.dataframe(
    pd.DataFrame(
        [{"Severity": SEVERITY_LABEL[sev], "Flag": label, "Indicator": key, "Rule": f"{op} {thr:g}",
          "Basis": config.FLAG_BASIS.get((key, thr), (None, "Seismograph line"))[1],
          "Reference": config.SOURCES[src].url if (src := config.FLAG_BASIS.get((key, thr), (None, ""))[0]) else None}
         for key, op, thr, sev, label in RED_FLAGS]
        + [{"Severity": "Watch", "Flag": "Political stability deteriorating", "Indicator": "wgi_pv",
            "Rule": f"falls ≥ {config.WGI_TREND_THRESHOLD:g} pts in {config.WGI_TREND_YEARS} years",
            "Basis": "Seismograph line, larger than most year-to-year noise in the WGI",
            "Reference": config.SOURCES["wgi_method"].url}]
    ),
    hide_index=True,
    column_config={"Basis": st.column_config.TextColumn(width="large"),
                   "Reference": st.column_config.LinkColumn(display_text="Open ↗")},
)
ui.cite("ucdp_def", "rr_inflation", "rr_debt", "freund", "imf_ara")
st.page_link(ui.SOURCES_PAGE, label="Every source and threshold reference", icon=":material/verified:")

st.header("7 · Robustness")
st.markdown(
    "Every country profile has a **sensitivity check** that recomputes the rank with equal weights and with each "
    "pillar dropped in turn. If a country's rank swings widely, the result depends on a modelling choice and should be "
    "presented with that caveat. WGI changes are tested against the WGI 90% confidence intervals, so the app can say "
    "whether a change is statistically clear or within the margin of error."
)

st.header("8 · Limitations")
st.markdown(
    """
* **Backward-looking data.** Governance data describe last year; conflict and displacement data lag by up to a year.
  Fast-moving events (a coup last month) will not show in the score — this is why the news pulse, the events
  watchlist and the analyst assessment exist.
* **Perception-based governance data.** The WGI aggregate expert and survey perceptions, with real margins of error.
  The WGI authors publish the six dimensions separately and do not combine them; combining them into a pillar here is
  a deliberate, documented choice.
* **Relative scoring.** Percentiles show position, not distance. A global shock that worsens every country can leave
  the ranking unchanged.
* **Missing data.** Small states and countries in conflict often have the least data — exactly where risk is highest.
  Check the coverage figure before drawing conclusions.
* **Equal weights within pillars, judgment-based weights across them.** Other choices are defensible; the
  sensitivity check shows how much they matter.
* **Not a forecast.** The index summarises structural conditions. Turning it into a probability of a specific event
  requires the analyst work the assessments are for.
"""
)

st.header("9 · How professional models compare")
st.markdown(
    """
* **ICRG (PRS Group)** — one of the longest-running commercial country-risk ratings; scores political, financial and
  economic risk separately and combines them, with political risk carrying the most points.
* **INFORM Risk Index (European Commission JRC)** — an open humanitarian-risk model built from hazard & exposure,
  vulnerability and lack of coping capacity, aggregated with geometric means. Its documentation is a model of
  transparency: [methodology](https://drmkc.jrc.ec.europa.eu/inform-index/INFORM-Risk/Methodology).
* **OECD Country Risk Classification** — export-credit agencies' 0–7 rating of the risk that a country cannot meet
  external debt payments, combining a quantitative model with expert judgment:
  [current list](https://www.oecd.org/en/topics/country-risk-classification).
* **Commercial intelligence firms** (Control Risks, Eurasia Group, Verisk Maplecroft, EIU and others) combine data
  models with networks of country analysts — the same split between model and judgment that this project uses.
"""
)

st.header("10 · Reproducibility")
st.markdown(
    "Every indicator, source, normalisation, weight and threshold is set out on this page, and all the data come "
    "from the public sources linked above — so anyone can recompute the scores."
)
ui.footer()
