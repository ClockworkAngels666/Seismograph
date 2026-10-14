"""Shared Streamlit UI pieces: sidebar, loading, badges, tables, footer."""

from __future__ import annotations

import html
import re

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from . import brand, config, content, data, globe, interpret
from .config import PILLARS, TIERS

WEIGHT_KEYS = {p.key: f"w_{p.key}" for p in PILLARS}
COUNTRY_PAGE = "app_pages/country.py"
COMPARE_PAGE = "app_pages/compare.py"
COMPARE_LIST = "compare_list"  # ISO3 codes picked for the Compare page, kept across pages


# ---------------------------------------------------------------------------
# Sidebar and weights
# ---------------------------------------------------------------------------
def _init_weights() -> None:
    for p in PILLARS:
        st.session_state.setdefault(WEIGHT_KEYS[p.key], p.default_weight)


def _reset_weights() -> None:
    for p in PILLARS:
        st.session_state[WEIGHT_KEYS[p.key]] = p.default_weight


def _refresh_data() -> None:
    data.refresh()


def _on_search() -> None:
    # Remember the pick and clear the box, so it is empty again on the next page
    st.session_state["_jump_to"] = st.session_state.get("country_search")
    st.session_state["country_search"] = None


def _country_search() -> None:
    try:
        countries = data.load_countries()
    except Exception:  # the search is a convenience; never let it break a page
        return
    options, names = country_options(countries)
    st.selectbox(
        "🔎 Find a country", options, index=None, key="country_search", on_change=_on_search,
        format_func=lambda i: names.get(i, i), placeholder="Type a country name…",
    )
    if jump := st.session_state.pop("_jump_to", None):
        go_to_country(jump)


def sidebar() -> None:
    _init_weights()
    with st.sidebar:
        st.caption(config.APP_TAGLINE)
        _country_search()
        st.page_link("app_pages/glossary.py", label="What does it all mean? Glossary & legend", icon=":material/help:")
        picked = st.session_state.get(COMPARE_LIST, [])
        if picked:
            st.page_link(COMPARE_PAGE, label=f"Your comparison ({len(picked)})", icon=":material/compare_arrows:")
        with st.expander("⚖️ Index weights", expanded=False):
            st.caption(
                "How much each pillar counts in the composite score. "
                "Weights are rescaled to 100%, so only their proportions matter."
            )
            for p in PILLARS:
                st.slider(p.label, min_value=0, max_value=100, step=5, key=WEIGHT_KEYS[p.key], help=p.question)
            w = weights()
            total = sum(w.values()) or 1
            st.caption(" · ".join(f"{p.short} {w[p.key] / total:.0%}" for p in PILLARS))
            st.button("Reset to defaults", on_click=_reset_weights)
        st.button(
            "↻ Refresh data", on_click=_refresh_data,
            help="Data is kept for 12 hours. This downloads the latest figures from every source in the "
                 "background; the page updates by itself when they arrive.",
        )
        st.caption(
            f"**{config.APP_TITLE}** · built by {config.AUTHOR}  \n"
            "Educational project — not investment or security advice."
        )


def weights() -> dict[str, float]:
    _init_weights()
    return {p.key: float(st.session_state[WEIGHT_KEYS[p.key]]) for p in PILLARS}


def weights_tuple() -> tuple[tuple[str, float], ...]:
    w = weights()
    if sum(w.values()) <= 0:
        w = {p.key: float(p.default_weight) for p in PILLARS}
    return tuple((p.key, w[p.key]) for p in PILLARS)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
@st.fragment(run_every=4)
def _wait_for_live_data(version: str) -> None:
    """While a live download runs, re-run the page as soon as the new data is ready."""
    status = data.live_status()
    if status["version"] and status["version"] != version:
        st.rerun(scope="app")


def load():
    """Load data and scores for the current weights. Stops the page with a message if impossible."""
    try:
        with st.spinner("Loading the data…"):
            core = data.load_core()
            year = data.analysis_year()
            values = data.get_values(core, year, core["version"])
            scores = data.get_scores(core, year, weights_tuple(), core["version"])
    except Exception as exc:  # show a friendly message instead of a stack trace
        st.error(
            "The data sources could not be reached and no snapshot is available yet. "
            "Please try again in a few minutes."
        )
        with st.expander("Technical details"):
            st.code(f"{type(exc).__name__}: {exc}")
        st.stop()
    status = data.live_status()
    if core["source"] == "snapshot":
        if status["running"]:
            st.info(
                f"⚡ Showing the saved data from {core.get('snapshot_date') or 'the last snapshot'} so the page opens "
                "instantly. The latest figures are downloading and will appear by themselves in about a minute.",
            )
        elif status["error"]:
            st.warning(
                f"The live sources can't be reached right now, so this is the saved data from "
                f"{core.get('snapshot_date') or 'the last snapshot'}. The app tries again every few minutes."
            )
    else:
        failed = [k for k, m in core["meta"].items() if m["error"] and not m["from_snapshot"]]
        snap = [k for k, m in core["meta"].items() if m["from_snapshot"]]
        if failed:
            st.warning(
                f"Some sources are temporarily unavailable ({', '.join(sorted(failed))}). "
                "Scores use the remaining indicators — see *Data status* at the bottom of the page."
            )
        elif snap:
            st.info(f"Some sources are being served from the saved snapshot ({', '.join(sorted(snap))}).")
    if status["running"] or (status["version"] and status["version"] != core["version"]):
        _wait_for_live_data(core["version"])
    return core, year, values, scores


def history(core: dict) -> pd.DataFrame:
    """The index for every year since config.HISTORY_START, with the current weights."""
    return data.get_history(core, weights_tuple(), core["version"])


@st.cache_data(ttl=600, show_spinner=False)
def assessments() -> dict[str, dict]:
    return content.load_assessments()


def master_table(core: dict, values: pd.DataFrame, scores: pd.DataFrame, hist: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per country with names, groups, flags, scores and analyst info (+ change vs last year)."""
    from . import scoring  # local import keeps module import order simple

    countries = core["countries"].set_index("iso3")
    table = countries[["name", "region", "income", "iso2", "lat", "lng"]].join(scores, how="left").join(
        values[["population", "gdppc", "battle_deaths_raw"]], how="left"
    )
    table["flag"] = table["iso2"].map(config.flag_url)
    if hist is not None and not hist.empty:
        last_year = int(hist["year"].max()) - 1
        prev = hist[hist["year"] == last_year].set_index("iso3")
        table["prev_composite"] = prev["composite"].reindex(table.index)
        table["prev_tier"] = prev["tier"].reindex(table.index)
        table["delta_1y"] = table["composite"] - table["prev_composite"]
        table["trend"] = table["delta_1y"].map(trend_label)
    table["flags"] = scoring.flag_counts(values).reindex(table.index).fillna(0).astype(int)
    a = assessments()
    table["assessment"] = table.index.map(lambda i: "✓" if i in a else "")
    table["analyst_rating"] = table.index.map(lambda i: a.get(i, {}).get("meta", {}).get("analyst_rating", ""))
    table["rank_label"] = table.apply(
        lambda r: f"{int(r['rank'])} of {int(r['n_ranked'])}" if pd.notna(r.get("rank")) else "not ranked", axis=1
    )
    return table.reset_index()


# ---------------------------------------------------------------------------
# Small components
# ---------------------------------------------------------------------------
TREND_THRESHOLD = 1.0  # score points; smaller year-on-year moves count as steady


def trend_label(delta) -> str:
    """Arrow + change vs last year. Up = riskier."""
    if delta is None or pd.isna(delta):
        return "—"
    if delta >= TREND_THRESHOLD:
        return f"▲ {delta:+.1f}"
    if delta <= -TREND_THRESHOLD:
        return f"▼ {delta:+.1f}"
    return f"■ {delta:+.1f}"


def flag_img(iso2, height: str = "1em") -> str:
    url = config.flag_url(iso2)
    if not url:
        return ""
    return (f'<img src="{url}" alt="" style="height:{height};aspect-ratio:4/3;border-radius:3px;'
            f'vertical-align:-0.12em;margin-right:0.35em;box-shadow:0 0 0 1px #2c2c2a">')


def country_heading(name: str, iso2, level: int = 1) -> None:
    """A page heading with the country's flag in front."""
    st.markdown(f"<h{level}>{flag_img(iso2, '0.85em')}{html.escape(str(name))}</h{level}>", unsafe_allow_html=True)


def _time_ago(ts) -> str:
    if ts is None or pd.isna(ts):
        return ""
    minutes = int((pd.Timestamp.now(tz="UTC") - ts).total_seconds() // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min ago"
    if minutes < 60 * 24:
        return f"{minutes // 60} h ago"
    return f"{minutes // (60 * 24)} d ago"


THUMB = "width:84px;height:56px;flex:none;border-radius:6px;object-fit:cover;background:#1a1a19"


def news_list(query_name: str | None, limit: int = 10, iso2=None) -> None:
    """Latest risk-related headlines with photos where the feed has one (the country flag otherwise).

    Bing News + Google News, GDELT as backup; cached for 10 minutes.
    """
    news = data.load_news(query_name)
    articles = news["articles"]
    if news["error"]:
        st.info("News is unavailable right now — every source refused the request. It retries automatically.")
        return
    if articles is None or articles.empty:
        st.info("No matching headlines in the last 7 days.")
        return
    fallback = config.flag_url(iso2)
    items = []
    for row in articles.head(limit).itertuples(index=False):
        url = str(row.url or "")
        title = html.escape(str(row.title or ""))
        link = f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{title}</a>' if url.startswith("http") else title
        meta = " · ".join(x for x in (html.escape(str(row.domain or "")), _time_ago(row.seen)) if x)
        image = row.image if isinstance(row.image, str) and row.image.startswith("https://") else None
        if image:
            thumb = f'<img src="{html.escape(image)}" alt="" loading="lazy" style="{THUMB}">'
        elif fallback:
            thumb = (f'<span style="{THUMB};display:flex;align-items:center;justify-content:center">'
                     f'<img src="{fallback}" alt="" style="width:40px;border-radius:3px;opacity:0.85"></span>')
        else:
            thumb = f'<span style="{THUMB};display:flex;align-items:center;justify-content:center;color:#5a5955">📰</span>'
        items.append(f'<li style="display:flex;gap:10px;align-items:flex-start;margin:0 0 0.85em 0;line-height:1.35">'
                     f'{thumb}<div>{link}<br><span style="color:#898781;font-size:0.8em">{meta}</span></div></li>')
    st.markdown(f'<ul style="list-style:none;padding:0;margin:0;font-size:0.88rem">{"".join(items)}</ul>',
                unsafe_allow_html=True)
    st.caption(f"{news['source']} · fetched {news['fetched']} · refreshes every 10 minutes. "
               "Automated and unfiltered — verify before citing.")


def tier_badge(tier: str | None, prefix: str = "") -> str:
    if not isinstance(tier, str) or tier not in config.TIER_ORDER:
        return '<span style="color:#898781">Not rated</span>'
    t = next(t for t in TIERS if t.label == tier)
    return (
        f'<span style="background:{t.color};color:{t.text_on};padding:3px 12px;border-radius:999px;'
        f'font-weight:600;font-size:0.9rem;white-space:nowrap">{prefix}{tier}</span>'
    )


def tier_legend() -> str:
    parts = [tier_badge(t.label) + f'<span style="color:#898781;font-size:0.8rem;margin:0 10px 0 4px">'
             f'{int(t.lower)}+</span>' for t in TIERS]
    return '<div style="line-height:2.2">' + "".join(parts) + "</div>"


def country_options(countries: pd.DataFrame) -> tuple[list[str], dict[str, str]]:
    names = dict(zip(countries["iso3"], countries["name"]))
    order = sorted(names, key=lambda i: names[i])
    return order, names


def current_country(countries: pd.DataFrame, fallback: str = "NGA") -> str:
    valid = set(countries["iso3"])
    for candidate in (st.session_state.get("country"), st.query_params.get("country"), fallback):
        if candidate and str(candidate).upper() in valid:
            return str(candidate).upper()
    return countries["iso3"].iloc[0]


def go_to_country(iso3: str) -> None:
    st.session_state["country"] = iso3
    st.switch_page(COUNTRY_PAGE)


def clicked_iso3(event) -> str | None:
    """ISO3 code of a clicked chart point. Clickable charts put it last in customdata."""
    points = getattr(getattr(event, "selection", None), "points", None) or []
    for point in points:
        custom = point.get("customdata")
        if isinstance(custom, (list, tuple)) and custom:
            return str(custom[-1])
    return None


def add_to_compare(iso3: str) -> None:
    picked = st.session_state.setdefault(COMPARE_LIST, [])
    if iso3 not in picked and len(picked) < config.MAX_COMPARE:
        picked.append(iso3)
    # Drop the Compare page's widget value so it re-reads the list next time it opens
    st.session_state.pop("compare_picked", None)


def hero(title: str, subtitle: str = "") -> None:
    """A page banner in the Seismograph style: a dark panel with the seismogram trace along the bottom."""
    st.markdown(
        '<div style="position:relative;overflow:hidden;background:linear-gradient(120deg,#0b1424 0%,#0d0d0d 55%,'
        '#1c0f0e 100%);border:1px solid #2c2c2a;border-radius:14px;padding:20px 26px 74px;margin:0 0 12px 0;'
        'color:#ffffff">'
        f'<div style="font-size:2rem;font-weight:700;line-height:1.2">{title}</div>'
        + (f'<div style="margin-top:6px;font-size:1.02rem;color:#c3c2b7">{subtitle}</div>' if subtitle else "")
        + f'<img src="{brand.data_uri("wave")}" alt="" style="position:absolute;left:0;right:0;bottom:10px;'
        'width:100%;height:58px"></div>',
        unsafe_allow_html=True,
    )


def brand_hero() -> None:
    """The Seismograph banner for the home page: mark, wordmark, tagline and the trace."""
    hero(
        f'<span style="display:inline-flex;align-items:center;gap:14px">'
        f'<img src="{brand.data_uri("icon")}" alt="" style="height:1.35em">'
        f'<span style="letter-spacing:0.08em">{config.APP_TITLE.upper()}</span></span>',
        config.APP_TAGLINE,
    )


def pillar_chip(pillar_key: str, text: str | None = None) -> str:
    """A small label in the pillar's colour, used to tie headings to the pillar charts and maps."""
    color = config.PILLAR_COLORS[pillar_key]
    label = text or config.PILLAR_BY_KEY[pillar_key].label
    return (
        f'<span style="display:inline-block;border-left:6px solid {color};background:{color}1f;'
        f'padding:2px 10px;border-radius:4px;font-weight:600">{label}</span>'
    )


def fmt_population(p) -> str:
    if p is None or pd.isna(p):
        return "—"
    if p >= 1e9:
        return f"{p / 1e9:.2f} bn"
    if p >= 1e6:
        return f"{p / 1e6:.1f} m"
    return f"{p / 1e3:.0f} k"


FLAG_COLUMN = st.column_config.ImageColumn(" ", width="small")
SOURCES_PAGE = "app_pages/sources.py"


def source_label(key: str) -> str:
    """The short name of a source, for inline citations."""
    return config.CITE_LABELS.get(key, config.SOURCES[key].name)


def source_link(key: str, label: str | None = None) -> str:
    """An HTML link to a source that opens in a new tab."""
    s = config.SOURCES[key]
    return (f'<a href="{html.escape(s.url)}" target="_blank" rel="noopener">'
            f'{html.escape(label or source_label(key))} ↗</a>')


def cite(*keys: str, note: str | None = None) -> None:
    """A linked "Sources:" line under a number, chart or table. Keys are config.SOURCES keys;
    "index" stands for the five datasets the risk index is built from."""
    expanded = [k for key in keys for k in (config.INDEX_SOURCES if key == "index" else [key])]
    links = [f"[{source_label(k)}]({config.SOURCES[k].url})" for k in dict.fromkeys(expanded)]
    st.caption("Sources: " + " · ".join(links) + (f" — {note}" if note else ""))


@st.fragment
def globe_panel(**kwargs) -> None:
    """A 3D globe in its own fragment, so clicking countries re-runs only the globe, not the whole page.

    Takes the arguments of globe.risk_globe; "Open full profile" goes to the country.
    """
    open_iso3, _ = globe.risk_globe(**kwargs)
    if open_iso3:
        go_to_country(open_iso3)


def _open_selected(event, frame: pd.DataFrame) -> None:
    if event and event.selection.rows:
        go_to_country(frame.iloc[event.selection.rows[0]]["iso3"])


def movers_lists(df: pd.DataFrame, n: int = 5, key: str = "movers") -> None:
    """Two clickable lists: the biggest rises and falls in the composite since last year."""
    valid = df.dropna(subset=["delta_1y"])
    risers = valid[valid["delta_1y"] >= TREND_THRESHOLD].nlargest(n, "delta_1y").reset_index(drop=True)
    fallers = valid[valid["delta_1y"] <= -TREND_THRESHOLD].nsmallest(n, "delta_1y").reset_index(drop=True)
    left, right = st.columns(2)
    for col, title, frame, part in ((left, "▲ Biggest risers (riskier)", risers, "up"),
                                    (right, "▼ Biggest fallers (safer)", fallers, "down")):
        with col:
            st.markdown(f"**{title}**")
            if frame.empty:
                st.caption("No country moved by a point or more.")
                continue
            event = st.dataframe(
                frame[["iso3", "flag", "name", "composite", "trend", "prev_tier", "tier"]], hide_index=True,
                on_select="rerun", selection_mode="single-row", key=f"{key}_{part}",
                column_config={
                    "iso3": None, "flag": FLAG_COLUMN, "name": "Country",
                    "composite": st.column_config.NumberColumn("Score", format="%.0f"),
                    "trend": "Change", "prev_tier": "Was", "tier": "Now",
                },
            )
            _open_selected(event, frame)


def country_table(df: pd.DataFrame, key: str, height: int | None = None, extra: dict | None = None) -> None:
    """A clickable ranking table (flag, score, change, tier, pillars); a click opens the profile."""
    cols = ["iso3", "flag", "name", "rank", "composite", "trend", "tier", *[p.key for p in PILLARS], *(extra or {})]
    frame = df.sort_values("rank", na_position="last")[[c for c in cols if c in df.columns]].reset_index(drop=True)
    event = st.dataframe(
        frame, hide_index=True, on_select="rerun", selection_mode="single-row", key=key, height=height,
        column_config={
            "iso3": None, "flag": FLAG_COLUMN, "name": st.column_config.TextColumn("Country", pinned=True),
            "rank": st.column_config.NumberColumn("Global rank", format="%d"),
            "composite": st.column_config.ProgressColumn("Composite", min_value=0, max_value=100, format="%.0f",
                                                         color=config.TIER_COLORS["Elevated"]),
            "trend": "1-yr change", "tier": "Tier",
            **{p.key: st.column_config.ProgressColumn(p.short, min_value=0, max_value=100, format="%.0f",
                                                      color=config.PILLAR_COLORS[p.key]) for p in PILLARS},
            **(extra or {}),
        },
    )
    _open_selected(event, frame)


def upcoming_events(events: pd.DataFrame, limit: int = 8) -> None:
    """Upcoming watchlist events with a countdown."""
    today = pd.Timestamp.today().normalize()
    upcoming = events[events["date"] >= today].sort_values("date").head(limit)
    if upcoming.empty:
        st.caption("No upcoming events in the watchlist.")
        return
    rows = []
    for e in upcoming.itertuples(index=False):
        days = (e.date - today).days
        when = "today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        colour = {"High": "#fd8078", "Medium": "#e19f3f"}.get(str(e.significance).title(), "#898781")
        source = (f' · <a href="{html.escape(e.source_url)}" target="_blank" rel="noopener">source</a>'
                  if str(e.source_url).startswith("http") else "")
        rows.append(
            f'<li style="margin:0 0 0.6em 0;line-height:1.35"><b>{html.escape(str(e.event))}</b><br>'
            f'<span style="color:#898781;font-size:0.82em">{html.escape(str(e.country))} · {e.date:%d %b %Y} · '
            f'<span style="color:{colour}">{when}</span> · {html.escape(str(e.significance))} significance{source}</span></li>'
        )
    st.markdown(f'<ul style="list-style:none;padding:0;margin:0;font-size:0.9rem">{"".join(rows)}</ul>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Video: live channels and the report / analysis gallery
# ---------------------------------------------------------------------------
def live_player(channel_id: str, height: int = 460) -> None:
    """A channel's current 24/7 live stream, through YouTube's official embed (privacy-enhanced domain)."""
    components.html(
        f'<iframe src="https://www.youtube-nocookie.com/embed/live_stream?channel={channel_id}&rel=0" '
        'style="width:100%;height:100%;border:0;border-radius:12px;background:#000" '
        'allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen '
        'referrerpolicy="strict-origin-when-cross-origin" title="Live news"></iframe>'
        '<style>html,body{margin:0;height:100%;background:transparent}</style>',
        height=height,
    )


def videos_about(videos: pd.DataFrame, iso3: str, names: dict[str, str], official: str | None = None) -> pd.DataFrame:
    """Videos whose title or description mentions a country (its name, news name, official name or aliases)."""
    name = names.get(iso3, iso3)
    terms = {name, config.NEWS_NAMES.get(iso3, name)} | ({official} if official else set())
    loose = [t for t in terms | set(config.VIDEO_ALIASES.get(iso3, [])) if not t.isupper()]
    exact = [t for t in config.VIDEO_ALIASES.get(iso3, []) if t.isupper()]
    pattern = re.compile(r"\b(" + "|".join(map(re.escape, sorted(loose, key=len, reverse=True))) + r")\b", re.I)
    pattern_exact = re.compile(r"\b(" + "|".join(map(re.escape, exact)) + r")\b") if exact else None
    # Longer country names that contain this one ("South Sudan" for Sudan) are removed before matching
    longer = [n for n in names.values() if n != name and name.lower() in n.lower()]
    strip = re.compile("|".join(map(re.escape, sorted(longer, key=len, reverse=True))), re.I) if longer else None

    def mentions(text: str) -> bool:
        text = strip.sub(" ", text) if strip else text
        return bool(pattern.search(text) or (pattern_exact and pattern_exact.search(text)))

    hits = (videos["title"].fillna("") + " \n " + videos["description"].fillna("")).map(mentions)
    return videos[hits]


@st.fragment
def video_gallery(videos: pd.DataFrame, key: str, limit: int = 9, columns: int = 3) -> None:
    """Thumbnails of videos; "▶ Play" shows the video in a player above the grid (only this section re-runs)."""
    shown = videos.head(limit).reset_index(drop=True)
    playing = st.session_state.get(f"{key}_playing")
    if playing in set(shown["video_id"]):
        current = shown[shown["video_id"] == playing].iloc[0]
        st.video(f"https://www.youtube.com/watch?v={playing}")
        st.caption(f"**{current['title']}** · {current['channel']} · {_time_ago(current['published'])}")
    cols = st.columns(columns)
    for i, v in shown.iterrows():
        with cols[i % columns], st.container(border=True):
            st.image(v["thumbnail"], width="stretch")
            url = f"https://www.youtube.com/watch?v={v['video_id']}"
            st.markdown(f"**[{v['title'].replace('[', '(').replace(']', ')')}]({url})**")
            views = f" · {v['views'] / 1000:,.0f}k views" if pd.notna(v.get("views")) and v["views"] >= 1000 else ""
            st.caption(f"{v['channel']} · {_time_ago(v['published'])}{views}")
            if st.button("▶ Play here", key=f"{key}_{v['video_id']}", width="stretch"):
                st.session_state[f"{key}_playing"] = v["video_id"]
                st.rerun(scope="fragment")


def render_reading(r: interpret.Reading, key: str) -> None:
    """A country's numbers translated into real life: on the ground, warning signs, direction, what to do."""
    st.markdown(f"{tier_badge(r.tier)} &nbsp; {html.escape(r.headline)}", unsafe_allow_html=True)
    if r.tier is None:
        st.info(r.ground)
        return
    left, right = st.columns([1.15, 1], gap="large")
    with left:
        st.markdown("#### What it looks like on the ground")
        st.markdown(r.ground)
        for d in r.drivers:
            with st.container(border=True):
                st.markdown(pillar_chip(d["pillar"], f"{d['label']} · {d['score']:.0f}/100"), unsafe_allow_html=True)
                st.markdown(d["ground"])
                if d["evidence"]:
                    st.caption("Driven by " + "; ".join(d["evidence"]) + ".")
                st.caption(f"Felt first by: {d['felt_by']}")
    with right:
        st.markdown("#### Warning signs right now")
        if r.warnings:
            for w in r.warnings:
                st.markdown(f"{config.SEVERITY_ICON[w['severity']]} **{w['label']}**  \n{w['meaning']}")
                st.caption(f"Typical response: {w['response']}")
        else:
            st.markdown("✅ No absolute warning thresholds crossed.")
        if r.near:
            st.markdown("#### Close to a red line")
            st.markdown("\n".join(f"- {n}" for n in r.near))
        if r.direction:
            st.markdown("#### Direction")
            st.markdown("\n".join(f"- {d}" for d in r.direction))
        st.markdown("#### Coming up")
        if r.events:
            st.markdown("\n".join(f"- {e}" for e in r.events))
        else:
            st.caption("No events in the watchlist for the next 12 months.")

    st.markdown("#### What to do with it")
    tabs = st.tabs(list(interpret.AUDIENCES.values()))
    for tab, audience in zip(tabs, interpret.AUDIENCES):
        with tab:
            st.markdown("\n".join(f"- {a}" for a in r.actions.get(audience, [])))
    st.download_button("⬇️ Download this reading (Markdown)", interpret.reading_markdown(r).encode("utf-8"),
                       file_name=f"{r.iso3}_real_life_reading.md", mime="text/markdown", key=f"{key}_download")
    st.caption(" ".join(r.caveats))


def data_status(core: dict) -> None:
    with st.expander("Data status and provenance"):
        rows = []
        for key, m in core["meta"].items():
            if m["error"] and not m["from_snapshot"]:
                status = "❌ Unavailable"
            elif m["from_snapshot"]:
                status = f"🗂️ Snapshot ({m.get('snapshot_date') or 'saved copy'})"
            else:
                status = "✅ Live"
            rows.append({
                "Series": key,
                "Provider": config.SOURCE_LABELS.get(m["provider"], m["provider"]),
                "Code": m["code"],
                "Source updated": m.get("edition") or m.get("last_updated") or "—",
                "Rows": m.get("rows", 0),
                "Status": status,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True)
        st.caption(f"Data loaded {core['loaded_at']}; cached for 12 hours.")
        errors = {k: m["error"] for k, m in core["meta"].items() if m["error"]}
        if errors:
            st.caption("Errors: " + " · ".join(f"**{k}**: {v[:160]}" for k, v in errors.items()))


def footer() -> None:
    st.divider()
    st.caption(
        f"**{config.APP_TITLE}** — {config.APP_DESCRIPTION} Data: World Bank Worldwide Governance Indicators & World "
        "Development Indicators · IMF World Economic Outlook · UNHCR · UCDP (via World Bank) · Bing News, Google News "
        "and GDELT. Scores are relative and model-based; they are a starting point for analysis, not a forecast. "
        f"Built by {config.AUTHOR}."
    )
    st.page_link(SOURCES_PAGE, label="Every source, with links and update dates", icon=":material/verified:")
