"""Track record: did the index flag countries before armed conflict broke out?

For every year t, take the countries *not* in armed conflict (fewer than 25 battle deaths, UCDP threshold) and check
which of them were in conflict in year t+1 (an "onset"). Then ask whether their risk score in year t was higher
than the others'. The scores come from the index recomputed for each year, using the data as published today.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CONFLICT_DEATHS = 25


def onset_panel(hist: pd.DataFrame, battle_deaths: pd.DataFrame, score: str = "stability") -> pd.DataFrame:
    """One row per country and year t: its score in t and whether armed conflict started in t+1."""
    if battle_deaths is None or battle_deaths.empty or hist.empty:
        return pd.DataFrame(columns=["iso3", "year", "score", "onset"])
    last = int(battle_deaths["year"].max())  # no conflict data after this year: don't count it as peace
    deaths = battle_deaths.pivot_table(index="iso3", columns="year", values="value", aggfunc="first")
    in_conflict = deaths.fillna(0) >= CONFLICT_DEATHS  # no recorded deaths = no conflict
    rows = []
    for year in sorted(hist["year"].unique()):
        if year + 1 > last:
            continue
        frame = hist[hist["year"] == year][["iso3", score]].dropna()
        now = in_conflict.get(year, pd.Series(dtype=bool)).reindex(frame["iso3"]).fillna(False).to_numpy(dtype=bool)
        nxt = in_conflict.get(year + 1, pd.Series(dtype=bool)).reindex(frame["iso3"]).fillna(False).to_numpy(dtype=bool)
        at_peace = ~now
        rows.append(pd.DataFrame({"iso3": frame["iso3"].to_numpy()[at_peace], "year": year,
                                  "score": frame[score].to_numpy()[at_peace], "onset": nxt[at_peace]}))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["iso3", "year", "score", "onset"])


def auc(scores: pd.Series, outcome: pd.Series) -> float | None:
    """Probability that a country where conflict started had a higher score than one where it did not (0.5 = chance)."""
    pos, neg = int(outcome.sum()), int((~outcome).sum())
    if not pos or not neg:
        return None
    ranks = scores.rank(method="average")
    return float((ranks[outcome].sum() - pos * (pos + 1) / 2) / (pos * neg))


def summary(panel: pd.DataFrame) -> dict:
    """Headline numbers and the onset rate in each fifth of the score distribution (fifths set within each year)."""
    if panel.empty:
        return {}
    panel = panel.copy()
    panel["fifth"] = panel.groupby("year")["score"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 5, labels=False) + 1)
    onsets = panel[panel["onset"]]
    by_fifth = panel.groupby("fifth")["onset"].agg(["mean", "sum", "size"]).reindex(range(1, 6))
    return {
        "years": (int(panel["year"].min()), int(panel["year"].max()) + 1),
        "cases": int(len(panel)),
        "onsets": int(len(onsets)),
        "base_rate": float(panel["onset"].mean()),
        "auc": auc(panel["score"], panel["onset"]),
        "top_fifth_share": float((onsets["fifth"] == 5).mean()) if len(onsets) else np.nan,
        "top_two_fifths_share": float((onsets["fifth"] >= 4).mean()) if len(onsets) else np.nan,
        "by_fifth": by_fifth,
        "onset_list": onsets.sort_values(["year", "score"], ascending=[True, False]),
    }
