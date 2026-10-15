"""Smoke tests: every page (and every country tab) runs without an error, using the saved data snapshot."""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest  # the `app` fixture comes from conftest.py

ROOT = Path(__file__).resolve().parents[1]
PAGES = re.findall(r'st\.Page\("(app_pages/[^"]+)"', (ROOT / "streamlit_app.py").read_text(encoding="utf-8"))
COUNTRY_TABS = ["Summary", "🧭 In real life", "Peers", "🌍 Map & refugee links", "🎛️ What-if simulator", "Indicators",
                "Governance trends", "Economy", "News pulse", "Analyst assessment"]


def errors(at: AppTest) -> list[str]:
    return [str(e.value)[:300] for e in at.exception]


def test_pages_are_found():
    assert len(PAGES) >= 18


@pytest.mark.parametrize("page", PAGES)
def test_page_runs(app, page):
    app.switch_page(page)
    app.run()
    assert not errors(app), errors(app)


@pytest.mark.parametrize("tab", COUNTRY_TABS)
def test_country_tab_runs(app, tab):
    app.switch_page("app_pages/country.py")
    app.session_state["country_tab"] = tab
    app.run()
    assert not errors(app), errors(app)


def test_country_picker_updates_the_dock(app):
    app.switch_page("app_pages/country.py")
    app.run()
    app.selectbox(key="country_pick").select("KEN").run()
    readout = next(m.value for m in app.markdown if 'class="sg-read' in m.value)
    assert "Kenya" in readout
