"""Data loading for the Streamlit app: instant start from the saved snapshot, live data in the background.

Downloading every API takes 40-60 seconds, and a free Streamlit app that has gone to sleep starts
cold. So pages render immediately from the snapshot CSVs in data/snapshot/ (refreshed monthly by
scripts/refresh_snapshot.py / the GitHub Action) while one background thread, shared by every
visitor, downloads the live figures. When they arrive, open pages re-run themselves (see
ui.load). Live data is kept for 12 hours; a series whose API is down keeps its snapshot copy.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from . import config, scoring, sources, validation

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "data" / "snapshot"
CACHE_TTL = 60 * 60 * 12
LIVE_START_DELAY = 4  # seconds


def _read_snapshot(name: str) -> pd.DataFrame | None:
    path = SNAPSHOT_DIR / f"{name}.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path)
    except Exception:  # a corrupt snapshot should never crash the app
        return None


def _snapshot_meta() -> dict:
    path = SNAPSHOT_DIR / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _with_country_columns(countries: pd.DataFrame) -> pd.DataFrame:
    """Older snapshots predate flags and capital coordinates."""
    countries = countries.copy()
    for col in ("iso2", "lat", "lng"):
        if col not in countries.columns:
            countries[col] = None
    return countries


def history_years() -> range:
    return range(config.HISTORY_START, analysis_year() + 1)


def build_default_history(series: dict[str, pd.DataFrame], countries: pd.DataFrame) -> pd.DataFrame:
    """The index for every year with the default weights: what almost every visitor sees, so it is built ahead."""
    return scoring.build_history(series, countries, scoring.default_weights(), history_years())


def _ready_history(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    """A saved history, if it covers exactly the years the app shows today."""
    if frame is None or frame.empty or "year" not in frame:
        return None
    return frame if sorted(frame["year"].unique()) == list(history_years()) else None


# ---------------------------------------------------------------------------
# Live download (runs in a background thread: no Streamlit calls in here)
# ---------------------------------------------------------------------------
def _fetch_live_core() -> dict:
    snapshot_meta = _snapshot_meta()
    try:
        countries, countries_from_snapshot = sources.fetch_wb_countries(), False
    except sources.SourceError:
        countries, countries_from_snapshot = _read_snapshot("countries"), True
        if countries is None:
            raise

    results = sources.fetch_many(config.RAW_SERIES)
    series: dict[str, pd.DataFrame] = {}
    meta: dict[str, dict] = {}
    for key, res in results.items():
        data, from_snapshot = res.data, False
        if res.error or data.empty:
            snap = _read_snapshot(key)
            if snap is not None and not snap.empty:
                data, from_snapshot = snap, True
        series[key] = data
        snap_info = snapshot_meta.get("series", {}).get(key, {})
        meta[key] = {
            "provider": res.provider,
            "code": res.code,
            "last_updated": res.last_updated or (snap_info.get("last_updated") if from_snapshot else None),
            "edition": res.edition or (snap_info.get("edition") if from_snapshot else None),
            "error": res.error,
            "from_snapshot": from_snapshot,
            "snapshot_date": snapshot_meta.get("created") if from_snapshot else None,
            "rows": int(len(data)),
        }
    try:
        flows = sources.fetch_unhcr_flows()
    except sources.SourceError:
        flows = _read_snapshot("flows")
    countries = _with_country_columns(countries)
    try:  # built here, in the background, so pages switch to live data without a pause
        history = build_default_history(series, countries)
    except Exception:
        history = None
    return {
        "countries": countries,
        "countries_from_snapshot": countries_from_snapshot,
        "series": series,
        "meta": meta,
        "flows": flows,
        "history_default": history,
        "loaded_at": dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
        "source": "live",
        "version": f"live-{time.time():.0f}",
    }


@st.cache_resource(show_spinner=False)
def _live_store() -> dict:
    """One per server process, shared by every visitor."""
    return {"core": None, "fetched_at": 0.0, "attempted_at": 0.0, "thread": None, "error": None,
            "lock": threading.Lock()}


def _download(store: dict) -> None:
    if store["core"] is None:
        # First download after the server starts: let the first visitor's page draw before competing for the CPU
        time.sleep(LIVE_START_DELAY)
    try:
        core = _fetch_live_core()
    except Exception as exc:  # keep serving what we have; ui.load reports it
        with store["lock"]:
            store["error"] = f"{type(exc).__name__}: {exc}"
        return
    with store["lock"]:
        store["core"], store["fetched_at"], store["error"] = core, time.time(), None


def _ensure_download(store: dict) -> None:
    with store["lock"]:
        now = time.time()
        stale = store["core"] is None or now - store["fetched_at"] > CACHE_TTL
        running = store["thread"] is not None and store["thread"].is_alive()
        recently_failed = store["error"] is not None and now - store["attempted_at"] < 300  # back off 5 min
        if stale and not running and not recently_failed:
            store["attempted_at"] = now
            store["thread"] = threading.Thread(target=_download, args=(store,), daemon=True, name="prm-live-data")
            store["thread"].start()


@st.cache_data(show_spinner=False)
def _snapshot_core() -> dict | None:
    """Everything from data/snapshot/, shaped like the live data."""
    countries = _read_snapshot("countries")
    if countries is None:
        return None
    snapshot_meta = _snapshot_meta()
    created = snapshot_meta.get("created")
    series, meta = {}, {}
    for key, (provider, code, _options) in config.RAW_SERIES.items():
        snap = _read_snapshot(key)
        info = snapshot_meta.get("series", {}).get(key, {})
        series[key] = snap if snap is not None else pd.DataFrame(columns=["iso3", "year", "value"])
        meta[key] = {
            "provider": provider,
            "code": code,
            "last_updated": info.get("last_updated"),
            "edition": info.get("edition"),
            "error": None if snap is not None else "not in the saved snapshot",
            "from_snapshot": snap is not None,
            "snapshot_date": created,
            "rows": 0 if snap is None else int(len(snap)),
        }
    return {
        "countries": _with_country_columns(countries),
        "countries_from_snapshot": True,
        "series": series,
        "meta": meta,
        "flows": _read_snapshot("flows"),
        "history_default": _ready_history(_read_snapshot("history")),
        "loaded_at": f"saved snapshot of {created}",
        "source": "snapshot",
        "snapshot_date": created,
        "version": f"snapshot-{created}",
    }


def load_core() -> dict:
    """Live data if it has been downloaded, otherwise the snapshot (a live download starts in the background)."""
    store = _live_store()
    _ensure_download(store)
    if store["core"] is not None:
        return store["core"]
    snapshot = _snapshot_core()
    if snapshot is not None:
        return snapshot
    # No snapshot at all (e.g. a fresh checkout): wait for the download
    if store["thread"] is not None:
        store["thread"].join()
    if store["core"] is None:
        raise sources.SourceError(store["error"] or "the live download failed")
    return store["core"]


def live_status() -> dict:
    store = _live_store()
    thread = store["thread"]
    return {
        "version": store["core"]["version"] if store["core"] else None,
        "running": thread is not None and thread.is_alive(),
        "error": store["error"],
    }


def refresh() -> None:
    """Start a fresh live download (the sidebar's Refresh button). Pages keep the current data meanwhile."""
    store = _live_store()
    with store["lock"]:
        store["fetched_at"] = 0.0
        store["error"] = None
    _ensure_download(store)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def load_wgi_ci() -> dict[str, pd.DataFrame]:
    """WGI 90% confidence intervals: the snapshot copy if complete (they change once a year), else live."""
    snap = {key: _read_snapshot(key) for key in config.WGI_CI_SERIES}
    if all(df is not None and not df.empty for df in snap.values()):
        return snap
    results = sources.fetch_many(config.WGI_CI_SERIES)
    return {
        key: res.data if not res.data.empty or snap.get(key) is None else snap[key]
        for key, res in results.items()
    }


def analysis_year() -> int:
    """The year the index describes: the current calendar year (IMF estimates)."""
    return dt.date.today().year


# Derived tables are cached per data version; `_core` (underscore) is not hashed by Streamlit.
@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=8)
def get_values(_core: dict, year: int, version: str) -> pd.DataFrame:
    return scoring.build_values(_core["series"], _core["countries"], year)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=32)
def get_scores(_core: dict, year: int, weights: tuple[tuple[str, float], ...], version: str) -> pd.DataFrame:
    return scoring.compute_scores(get_values(_core, year, version), dict(weights))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=16)
def get_track_record(_core: dict, weights: tuple[tuple[str, float], ...], version: str, score: str) -> dict:
    """Did high scores come before armed conflict? (see prm/validation.py)"""
    panel = validation.onset_panel(get_history(_core, weights, version), _core["series"].get("battle_deaths"), score)
    return validation.summary(panel)


@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=64)
def get_sensitivity(_core: dict, year: int, iso3: str, weights: tuple[tuple[str, float], ...],
                    version: str) -> pd.DataFrame:
    """A country's score with equal weights and with each pillar left out (five full recomputes, so cached)."""
    return scoring.sensitivity(get_values(_core, year, version), iso3, dict(weights))


@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=16)
def get_history(_core: dict, weights: tuple[tuple[str, float], ...], version: str) -> pd.DataFrame:
    if dict(weights) == scoring.default_weights() and _core.get("history_default") is not None:
        return _core["history_default"]  # built ahead of time (snapshot or live download)
    return scoring.build_history(_core["series"], _core["countries"], dict(weights), history_years())


@st.cache_data(ttl=60 * 10, show_spinner=False)
def load_news(name: str | None) -> dict:
    """Headlines for a country (None = global), cached for 10 minutes per country."""
    fetched = dt.datetime.now(dt.timezone.utc).strftime("%H:%M UTC")
    try:
        articles, source = sources.fetch_news(name)
        return {"articles": articles, "error": None, "source": source, "fetched": fetched}
    except sources.SourceError as exc:
        return {"articles": None, "error": str(exc), "source": "", "fetched": fetched}


@st.cache_data(ttl=60 * 15, show_spinner=False)
def load_videos() -> pd.DataFrame | None:
    """Latest news reports, think-tank analysis and institutions' videos (YouTube feeds), cached for 15 minutes."""
    frames = []
    for kind, channels in (("news", config.NEWS_VIDEO_CHANNELS), ("analysis", config.ANALYSIS_VIDEO_CHANNELS),
                           ("institutions", config.INSTITUTION_VIDEO_CHANNELS)):
        try:
            frames.append(sources.fetch_videos(channels, kind))
        except sources.SourceError:
            continue
    return pd.concat(frames, ignore_index=True) if frames else None


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_tone(name: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return sources.fetch_gdelt_tone(name), None
    except sources.SourceError as exc:
        return None, str(exc)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def load_protests(name: str) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return sources.fetch_gdelt_protests(name), None
    except sources.SourceError as exc:
        return None, str(exc)


@st.cache_data(ttl=60 * 60 * 24 * 7, show_spinner=False)
def load_fsi() -> tuple[pd.DataFrame | None, str | None]:
    """The Fragile States Index edition in config.FSI_URL, matched to our country codes (cached for a week)."""
    try:
        return sources.fetch_fsi(config.FSI_URL, load_countries()), None
    except sources.SourceError as exc:
        return None, str(exc)


def load_countries() -> pd.DataFrame:
    """Just the country list — powers the sidebar search on every page."""
    return load_core()["countries"]


def country_series(series: dict[str, pd.DataFrame], key: str, iso3: str) -> pd.DataFrame:
    df = series.get(key)
    if df is None or df.empty:
        return pd.DataFrame(columns=["year", "value"])
    return df[df["iso3"] == iso3][["year", "value"]].sort_values("year")
