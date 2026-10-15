"""Unit tests for the scoring model and the analysis helpers (fast, no network)."""

import numpy as np
import pandas as pd
import pytest

from prm import cases, config, data, glossary, report, scoring, validation


@pytest.fixture(scope="module")
def core():
    snapshot = data._snapshot_core()
    assert snapshot is not None, "data/snapshot is missing"
    return snapshot


@pytest.fixture(scope="module")
def values(core):
    return scoring.build_values(core["series"], core["countries"], data.analysis_year())


def test_scores_are_on_a_0_to_100_scale(values):
    scores = scoring.compute_scores(values)
    for col in ["composite", *[p.key for p in config.PILLARS]]:
        s = scores[col].dropna()
        assert len(s) > 150, f"too few countries scored on {col}"
        assert s.between(0, 100).all(), col
    assert set(scores["tier"].dropna()) <= set(config.TIER_ORDER)


def test_riskier_composite_means_a_better_rank(values):
    scores = scoring.compute_scores(values).dropna(subset=["composite"]).sort_values("composite", ascending=False)
    assert scores["rank"].is_monotonic_increasing


def test_weights_change_the_composite(values):
    stability_only = {p.key: (100.0 if p.key == "stability" else 0.0) for p in config.PILLARS}
    a = scoring.compute_scores(values)
    b = scoring.compute_scores(values, stability_only)
    both = a[["composite", "stability"]].join(b["composite"].rename("only"), how="inner").dropna()
    assert not np.allclose(both["composite"], both["only"])
    assert np.allclose(both["only"], both["stability"])


def test_red_flag_thresholds():
    row = pd.Series({"inflation": 25.0, "gov_debt": 120.0, "reserves_months": 1.5, "battle_deaths_raw": 2000})
    labels = {f["key"]: f["severity"] for f in scoring.red_flags(row)}
    assert labels["inflation"] == "serious"
    assert labels["gov_debt"] == "warning"
    assert labels["reserves_months"] == "serious"
    assert labels["battle_deaths_raw"] == "critical"
    assert scoring.red_flags(pd.Series({"inflation": 3.0})) == []


def test_saved_history_matches_a_fresh_build(core):
    if core.get("history_default") is None:
        pytest.skip("no saved history in the snapshot")
    fresh = data.build_default_history(core["series"], core["countries"])
    saved = core["history_default"]
    merged = fresh.merge(saved, on=["iso3", "year"], suffixes=("", "_saved"))
    assert len(merged) == len(fresh)
    assert np.allclose(merged["composite"].fillna(-1), merged["composite_saved"].fillna(-1), atol=1e-6)


def test_auc():
    scores = pd.Series([1, 2, 3, 4])
    assert validation.auc(scores, pd.Series([False, False, True, True])) == 1.0
    assert validation.auc(scores, pd.Series([True, True, False, False])) == 0.0
    assert validation.auc(scores, pd.Series([False] * 4)) is None


def test_onset_panel_counts_new_conflicts_only():
    hist = pd.DataFrame({"iso3": ["A", "B", "C"] * 2, "year": [2020] * 3 + [2021] * 3,
                         "stability": [80, 20, 50, 80, 20, 50]})
    deaths = pd.DataFrame({"iso3": ["A", "C", "C"], "year": [2021, 2020, 2021], "value": [100, 500, 500]})
    panel = validation.onset_panel(hist, deaths)
    # 2020 -> 2021 only (no data after 2021); C was already at war in 2020, so it is not a candidate
    assert set(panel["iso3"]) == {"A", "B"}
    assert panel.set_index("iso3").loc["A", "onset"] and not panel.set_index("iso3").loc["B", "onset"]


def test_track_record_beats_chance(core):
    panel = validation.onset_panel(core["history_default"], core["series"]["battle_deaths"])
    result = validation.summary(panel)
    assert result["onsets"] > 10
    assert result["auc"] > 0.6, "the stability pillar should rank countries before new conflicts better than chance"


def test_case_studies_have_readings(core):
    for case in cases.CASES:
        before = int(case.date[:4]) - 1
        reading = cases.reading(case, core["history_default"], scoring.build_values(core["series"], core["countries"], before))
        assert reading["verdict"] in cases.VERDICTS, case.key


def test_pdf_brief(core, values):
    from prm import content, interpret, ui
    year = data.analysis_year()
    scores = scoring.compute_scores(values)
    hist = core["history_default"]
    table = ui.master_table(core, values, scores, hist)
    reading = interpret.country_reading("NGA", table, values, scores, hist, content.load_events(), core.get("flows"), year)
    pdf = report.country_pdf(reading, table.set_index("iso3").loc["NGA"], hist[hist["iso3"] == "NGA"],
                             scoring.red_flags(values.loc["NGA"]), year)
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000


def test_every_glossary_category_is_styled():
    terms = glossary.all_terms()
    assert set(terms) <= set(glossary.CATEGORIES)
    assert sum(len(v) for v in terms.values()) >= 100


def test_every_cited_source_exists():
    keys = [k for group in config.SOURCE_GROUPS.values() for k in group]
    keys += [k for group in config.CROSS_CHECKS.values() for k in group]
    keys += [s for s, _ in config.FLAG_BASIS.values() if s]
    keys += [k for c in glossary.CATEGORIES.values() for k in c.sources] + list(glossary.TERM_SOURCES.values())
    assert set(keys) <= set(config.SOURCES)
