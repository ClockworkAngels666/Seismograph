"""Data fetchers for the public APIs Seismograph uses.

This module has no Streamlit dependency, so the same functions power the app
(through the cached loaders in data.py) and the snapshot script in scripts/.

Every fetcher returns tidy "long" data: one row per country-year with the
columns iso3, year, value.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pandas as pd
import requests

from . import config

TIMEOUT = 45
HEADERS = {"User-Agent": "seismograph/1.0 (open-source student project)"}
# The IMF's CDN (Akamai) answers 403 to custom User-Agent strings, so IMF calls keep the requests default
IMF_HEADERS: dict[str, str] = {}

WB_API = "https://api.worldbank.org/v2"
IMF_API = "https://www.imf.org/external/datamapper/api/v1"
UNHCR_API = "https://api.unhcr.org/population/v1/population/"
GDELT_API = "https://api.gdeltproject.org/api/v2/doc/doc"
YOUTUBE_FEED = "https://www.youtube.com/feeds/videos.xml"
_YT_NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015",
          "media": "http://search.yahoo.com/mrss/"}
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
BING_NEWS_RSS = "https://www.bing.com/news/search"
NEWS_COLUMNS = ["seen", "title", "domain", "url", "image"]


class SourceError(RuntimeError):
    """Raised when an API is unreachable or answers with an error."""


@dataclass
class SeriesResult:
    key: str
    data: pd.DataFrame  # iso3, year, value
    provider: str
    code: str
    last_updated: str | None = None
    edition: str | None = None
    error: str | None = None
    from_snapshot: bool = False
    fetched_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"))


def _empty() -> pd.DataFrame:
    return pd.DataFrame({"iso3": pd.Series(dtype=str), "year": pd.Series(dtype=int), "value": pd.Series(dtype=float)})


def _get_json(url: str, params: dict | None = None, retries: int = 2, headers: dict[str, str] = HEADERS):
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT, headers=headers)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise SourceError(f"{url} — {last_error}")


def _num(value) -> float:
    """UNHCR returns numbers, numeric strings or '-' for zero/not applicable."""
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# World Bank
# ---------------------------------------------------------------------------
def fetch_wb_countries() -> pd.DataFrame:
    """Country list with region and income group (aggregates removed)."""
    data = _get_json(f"{WB_API}/country", {"format": "json", "per_page": 500})
    if not isinstance(data, list) or len(data) < 2 or not data[1]:
        raise SourceError(f"World Bank country list: unexpected response {str(data)[:200]}")
    rows = []
    for c in data[1]:
        region = (c.get("region") or {}).get("value", "")
        if not region or region == "Aggregates":
            continue
        iso3 = c.get("id", "")
        rows.append(
            {
                "iso3": iso3,
                "iso2": c.get("iso2Code", ""),
                "name": config.DISPLAY_NAMES.get(iso3, c.get("name", iso3)),
                "official_name": c.get("name", iso3),
                "region": region.strip(),
                "income": (c.get("incomeLevel") or {}).get("value", "").strip() or "Not classified",
                "capital": c.get("capitalCity", ""),
                # Capital coordinates: used to place small states, conflict rings and refugee arcs on the globe
                "lat": pd.to_numeric(c.get("latitude"), errors="coerce"),
                "lng": pd.to_numeric(c.get("longitude"), errors="coerce"),
            }
        )
    for iso3, extra in config.EXTRA_ECONOMIES.items():
        if iso3 not in {r["iso3"] for r in rows}:
            rows.append({"iso3": iso3, "official_name": extra["name"], **extra})
    return pd.DataFrame(rows).sort_values("name").reset_index(drop=True)


def fetch_wb_indicator(key: str, code: str, source: int | None = None, start: int = 1996) -> SeriesResult:
    end = dt.date.today().year
    params = {"format": "json", "per_page": 20000, "date": f"{start}:{end}"}
    if source:
        params["source"] = source
    rows, page, last_updated = [], 1, None
    while True:
        params["page"] = page
        data = _get_json(f"{WB_API}/country/all/indicator/{code}", params)
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            message = data[0].get("message") if isinstance(data, list) and data and isinstance(data[0], dict) else data
            raise SourceError(f"World Bank {code}: {str(message)[:200]}")
        meta, records = data[0], data[1]
        last_updated = meta.get("lastupdated", last_updated)
        for r in records:
            value = r.get("value")
            if value is None:
                continue
            iso3 = r.get("countryiso3code") or config.WB_NAME_TO_ISO3.get((r.get("country") or {}).get("value", ""))
            if not iso3:
                continue
            try:
                rows.append((iso3, int(str(r.get("date"))[:4]), float(value)))
            except (TypeError, ValueError):
                continue
        if page >= int(meta.get("pages", 1) or 1):
            break
        page += 1
    df = pd.DataFrame(rows, columns=["iso3", "year", "value"]) if rows else _empty()
    return SeriesResult(key, df, "WB", code, last_updated=last_updated)


# ---------------------------------------------------------------------------
# IMF World Economic Outlook (DataMapper API)
# ---------------------------------------------------------------------------
def fetch_imf_editions() -> dict[str, str]:
    """Return {indicator code: source label}, e.g. 'World Economic Outlook (October 2026)'."""
    data = _get_json(f"{IMF_API}/indicators", headers=IMF_HEADERS)
    return {code: (meta or {}).get("source", "") for code, meta in (data.get("indicators") or {}).items()}


def fetch_imf_indicator(key: str, code: str, edition: str | None = None) -> SeriesResult:
    data = _get_json(f"{IMF_API}/{code}", headers=IMF_HEADERS)
    series = (data.get("values") or {}).get(code) or {}
    if not series:
        raise SourceError(f"IMF {code}: no values returned")
    rows = []
    for iso3, by_year in series.items():
        iso3 = config.IMF_TO_WB_ISO3.get(iso3, iso3)
        for year, value in (by_year or {}).items():
            if value is None:
                continue
            try:
                rows.append((iso3, int(year), float(value)))
            except (TypeError, ValueError):
                continue
    df = pd.DataFrame(rows, columns=["iso3", "year", "value"]) if rows else _empty()
    return SeriesResult(key, df, "IMF", code, edition=edition)


# ---------------------------------------------------------------------------
# UNHCR
# ---------------------------------------------------------------------------
def _unhcr_pages(params: dict) -> list[dict]:
    items, page, max_pages = [], 1, 1
    while page <= max_pages:
        data = _get_json(UNHCR_API, {**params, "cf_type": "ISO", "limit": 1000, "page": page})
        max_pages = int(data.get("maxPages", 1) or 1)
        items.extend(data.get("items", []) or [])
        page += 1
    return items


def _iso(value) -> str | None:
    value = str(value or "")
    return value if len(value) == 3 and value != "-" else None


def fetch_unhcr_displacement(key: str = "displaced", years: int = 13) -> SeriesResult:
    """Forcibly displaced people by country of origin, for each of the last `years` published years."""
    this_year = dt.date.today().year
    items = _unhcr_pages({"yearFrom": this_year - years, "yearTo": this_year - 1, "coo_all": "true"})
    rows = []
    for item in items:
        iso3 = _iso(item.get("coo_iso") or item.get("coo"))
        if iso3 and item.get("year"):
            total = sum(_num(item.get(f)) for f in ("refugees", "asylum_seekers", "oip", "idps"))
            rows.append((iso3, int(item["year"]), total))
    if not rows:
        raise SourceError("UNHCR: no displacement data found")
    df = pd.DataFrame(rows, columns=["iso3", "year", "value"]).groupby(["iso3", "year"], as_index=False)["value"].sum()
    return SeriesResult(key, df, "UNHCR", "population", last_updated=str(int(df["year"].max())))


def fetch_unhcr_flows() -> pd.DataFrame:
    """Refugees, asylum seekers and others in need of protection by origin -> host, latest published year.

    Columns: origin, host, year, value. IDPs are excluded (they never cross a border).
    """
    this_year = dt.date.today().year
    for year in (this_year - 1, this_year - 2):
        rows = []
        for item in _unhcr_pages({"year": year, "coo_all": "true", "coa_all": "true"}):
            origin, host = _iso(item.get("coo_iso")), _iso(item.get("coa_iso"))
            if origin and host and origin != host:
                value = sum(_num(item.get(f)) for f in ("refugees", "asylum_seekers", "oip"))
                if value > 0:
                    rows.append((origin, host, year, value))
        if rows:
            df = pd.DataFrame(rows, columns=["origin", "host", "year", "value"])
            return df.groupby(["origin", "host", "year"], as_index=False)["value"].sum()
    raise SourceError("UNHCR: no refugee flow data found")


# ---------------------------------------------------------------------------
# Bulk loader
# ---------------------------------------------------------------------------
def fetch_series(key: str, spec: tuple[str, str, dict], imf_editions: dict[str, str] | None = None) -> SeriesResult:
    provider, code, options = spec
    try:
        if provider == "WB":
            return fetch_wb_indicator(key, code, source=options.get("source"))
        if provider == "IMF":
            return fetch_imf_indicator(key, code, edition=(imf_editions or {}).get(code))
        if provider == "UNHCR":
            return fetch_unhcr_displacement(key)
        raise SourceError(f"Unknown provider {provider}")
    except SourceError as exc:
        return SeriesResult(key, _empty(), provider, code, error=str(exc))
    except Exception as exc:  # never let one source take the whole app down
        return SeriesResult(key, _empty(), provider, code, error=f"{type(exc).__name__}: {exc}")


def fetch_many(specs: dict[str, tuple[str, str, dict]], max_workers: int = 6) -> dict[str, SeriesResult]:
    """Fetch several series in parallel. Failed series come back empty with .error set."""
    imf_editions: dict[str, str] = {}
    if any(spec[0] == "IMF" for spec in specs.values()):
        try:
            imf_editions = fetch_imf_editions()
        except SourceError:
            imf_editions = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {key: pool.submit(fetch_series, key, spec, imf_editions) for key, spec in specs.items()}
        return {key: future.result() for key, future in futures.items()}


# ---------------------------------------------------------------------------
# News: Bing News RSS (has thumbnails) + Google News RSS (more headlines), merged; GDELT as the fallback
# ---------------------------------------------------------------------------
RISK_TERMS = "(protest OR election OR coup OR sanctions OR clashes OR unrest OR strike OR attack OR default)"
GLOBAL_NEWS_QUERY = (
    '(coup OR ceasefire OR sanctions OR insurgency OR "state of emergency" OR "mass protests" OR '
    '"armed clashes" OR "snap election" OR "martial law")'
)


def fetch_google_news(name: str | None, days: int = 7, max_records: int = 25) -> pd.DataFrame:
    """Recent risk-related headlines for a country (or global ones when name is None)."""
    query = f"{_gdelt_term(name)} {RISK_TERMS}" if name else GLOBAL_NEWS_QUERY
    params = {"q": f"{query} when:{days}d", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    try:
        response = requests.get(GOOGLE_NEWS_RSS, params=params, timeout=20, headers=HEADERS)
        response.raise_for_status()
        channel = ET.fromstring(response.content).find("channel")
    except (requests.RequestException, ET.ParseError) as exc:
        raise SourceError(f"Google News unreachable: {exc}") from exc
    rows = []
    for item in channel.findall("item") if channel is not None else []:
        source = (item.findtext("source") or "").strip()
        title = (item.findtext("title") or "").strip()
        if source and title.endswith(f" - {source}"):  # titles repeat the outlet name at the end
            title = title[: -len(source) - 3].strip()
        rows.append({"seen": _rss_date(item.findtext("pubDate")), "title": title, "domain": source,
                     "url": item.findtext("link") or "", "image": None})
    return _news_frame(rows, max_records)


def _rss_date(text: str | None):
    try:
        return pd.Timestamp(email.utils.parsedate_to_datetime(text or ""))
    except (TypeError, ValueError):
        return pd.NaT


def _news_frame(rows: list[dict], max_records: int) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=NEWS_COLUMNS)
    df = pd.DataFrame(rows)
    df["seen"] = pd.to_datetime(df["seen"], utc=True, errors="coerce")
    df = df.drop_duplicates(subset="title").sort_values("seen", ascending=False)
    return df.head(max_records)[NEWS_COLUMNS].reset_index(drop=True)


def fetch_bing_news(name: str | None, max_records: int = 15) -> pd.DataFrame:
    """Recent headlines from Bing News, most with a thumbnail photo (English, US market)."""
    query = f"{_gdelt_term(name)} {RISK_TERMS}" if name else GLOBAL_NEWS_QUERY
    params = {"q": query, "format": "rss", "mkt": "en-US", "setlang": "en-US", "cc": "US", "qft": 'sortbydate="1"'}
    try:
        response = requests.get(BING_NEWS_RSS, params=params, timeout=20, headers=HEADERS)
        response.raise_for_status()
        channel = ET.fromstring(response.content).find("channel")
    except (requests.RequestException, ET.ParseError) as exc:
        raise SourceError(f"Bing News unreachable: {exc}") from exc
    rows = []
    for item in channel.findall("item") if channel is not None else []:
        extra = {child.tag.split("}")[-1]: (child.text or "").strip() for child in item}  # News:Source, News:Image
        image = extra.get("Image") or None
        if image:  # https (the app is served over https) and a small, centre-cropped thumbnail
            image = image.replace("http://", "https://", 1) + "&w=200&h=130&c=7&rs=1"
        rows.append({"seen": _rss_date(item.findtext("pubDate")), "title": (item.findtext("title") or "").strip(),
                     "domain": extra.get("Source", "").removesuffix(" on MSN"), "url": item.findtext("link") or "",
                     "image": image})
    return _news_frame(rows, max_records)


def _title_key(title: str) -> str:
    return "".join(ch for ch in str(title).lower() if ch.isalnum())[:60]


def fetch_news(name: str | None) -> tuple[pd.DataFrame, str]:
    """(headlines, source label). Merges Bing (photos) and Google News; GDELT if both fail."""
    frames, used, errors = [], [], []
    for label, fetch in (("Bing News", fetch_bing_news), ("Google News", fetch_google_news)):
        try:
            df = fetch(name)
            if not df.empty:
                frames.append(df)
                used.append(label)
        except SourceError as exc:
            errors.append(str(exc))
    if frames:
        merged = pd.concat(frames, ignore_index=True)
        # The same story often appears in both feeds: keep one copy, preferring the one with a photo
        merged = merged.assign(key=merged["title"].map(_title_key), has_image=merged["image"].notna())
        merged = merged.sort_values("has_image", ascending=False).drop_duplicates("key")
        # Newest day first; within a day, stories with a photo first
        merged = merged.assign(day=merged["seen"].dt.floor("D")).sort_values(
            ["day", "has_image", "seen"], ascending=[False, False, False], na_position="last"
        )
        return merged[NEWS_COLUMNS].head(30).reset_index(drop=True), " + ".join(used)
    if name:
        try:
            return fetch_gdelt_articles(name)[NEWS_COLUMNS], "GDELT"
        except SourceError as exc:
            errors.append(str(exc))
    if errors:
        raise SourceError(" | ".join(errors)[:300])
    return pd.DataFrame(columns=NEWS_COLUMNS), "Google News"


def _gdelt_term(name: str) -> str:
    if name.startswith("("):  # already a search expression, e.g. config.REGION_NEWS
        return name
    clean = name.replace("'", " ").replace('"', "").strip()
    return f'"{clean}"' if " " in clean else clean


def fetch_gdelt_articles(name: str, timespan: str = "7d", max_records: int = 25) -> pd.DataFrame:
    params = {
        "query": f"{_gdelt_term(name)} {RISK_TERMS} sourcelang:english",
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_records,
        "timespan": timespan,
        "sort": "DateDesc",
    }
    try:
        response = requests.get(GDELT_API, params=params, timeout=25, headers=HEADERS)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SourceError(f"GDELT unreachable: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        # GDELT answers rate limits and query errors in plain text
        raise SourceError(response.text.strip()[:200] or "GDELT returned no data") from exc
    articles = data.get("articles") or []
    if not articles:
        return pd.DataFrame(columns=[*NEWS_COLUMNS, "sourcecountry"])
    df = pd.DataFrame(articles)
    for col in ("title", "domain", "url", "sourcecountry", "seendate", "socialimage"):
        if col not in df.columns:
            df[col] = ""
    df["seen"] = pd.to_datetime(df["seendate"], format="%Y%m%dT%H%M%SZ", errors="coerce", utc=True)
    df["image"] = df["socialimage"].where(df["socialimage"].str.startswith("https://", na=False))
    df = df.drop_duplicates(subset="title").sort_values("seen", ascending=False)
    return df[[*NEWS_COLUMNS, "sourcecountry"]].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Video: latest uploads of broadcasters' and think tanks' YouTube channels (official RSS, no API key)
# ---------------------------------------------------------------------------
def fetch_youtube_feed(channel_id: str) -> pd.DataFrame:
    """The ~15 most recent videos of one channel: id, title, published, description, views, thumbnail."""
    try:
        response = requests.get(YOUTUBE_FEED, params={"channel_id": channel_id}, timeout=20, headers=HEADERS)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError) as exc:
        raise SourceError(f"YouTube feed {channel_id}: {exc}") from exc
    rows = []
    for entry in root.findall("a:entry", _YT_NS):
        video_id = entry.findtext("yt:videoId", default="", namespaces=_YT_NS)
        group = entry.find("media:group", _YT_NS)
        stats = group.find("media:community/media:statistics", _YT_NS) if group is not None else None
        rows.append({
            "video_id": video_id,
            "title": entry.findtext("a:title", default="", namespaces=_YT_NS),
            "published": entry.findtext("a:published", default="", namespaces=_YT_NS),
            "description": (group.findtext("media:description", default="", namespaces=_YT_NS) if group is not None
                            else "")[:600],
            "views": pd.to_numeric(stats.get("views"), errors="coerce") if stats is not None else None,
            "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        })
    df = pd.DataFrame(rows, columns=["video_id", "title", "published", "description", "views", "thumbnail"])
    df["published"] = pd.to_datetime(df["published"], utc=True, errors="coerce")
    return df


def fetch_videos(channels: dict[str, str], kind: str) -> pd.DataFrame:
    """Latest videos of several channels, newest first, with the channel name and kind ("news"/"analysis")."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {name: pool.submit(fetch_youtube_feed, cid) for name, cid in channels.items()}
    frames = []
    for name, future in futures.items():
        try:
            frames.append(future.result().assign(channel=name, kind=kind))
        except SourceError:
            continue  # one channel down never hides the others
    if not frames:
        raise SourceError("No video feed could be loaded")
    return pd.concat(frames, ignore_index=True).sort_values("published", ascending=False, ignore_index=True)


def fetch_gdelt_tone(name: str, timespan: str = "3m") -> pd.DataFrame:
    params = {
        "query": f"{_gdelt_term(name)} sourcelang:english",
        "mode": "TimelineTone",
        "format": "json",
        "timespan": timespan,
    }
    try:
        response = requests.get(GDELT_API, params=params, timeout=25, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise SourceError(f"GDELT unreachable: {exc}") from exc
    except ValueError as exc:
        raise SourceError(response.text.strip()[:200] or "GDELT returned no data") from exc
    timeline = data.get("timeline") or []
    points = timeline[0].get("data", []) if timeline else []
    if not points:
        return pd.DataFrame(columns=["date", "tone"])
    df = pd.DataFrame(points).rename(columns={"value": "tone"})
    df["date"] = pd.to_datetime(df["date"], format="%Y%m%dT%H%M%SZ", errors="coerce", utc=True)
    return df.dropna(subset=["date"])[["date", "tone"]]
