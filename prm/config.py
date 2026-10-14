"""Central configuration: data series, indicators, pillars, tiers and display names.

Everything the app scores is defined here, so the methodology page, the scoring
engine and the charts all read from one source of truth. To add an indicator,
add its raw series to RAW_SERIES and an entry to INDICATORS.
"""

from __future__ import annotations

from dataclasses import dataclass, field

APP_TITLE = "Seismograph"
APP_TAGLINE = "Picking up political tremors before they become earthquakes."
APP_DESCRIPTION = (
    "A transparent country risk index built from open data — "
    "with an analyst's judgment on top."
)
AUTHOR = "Tuan Dung Nguyen"  # shown in the footer and on assessments

# ---------------------------------------------------------------------------
# Source links (used on the Methodology and Resources pages)
# ---------------------------------------------------------------------------
URL_WGI = "https://www.worldbank.org/en/publication/worldwide-governance-indicators"
URL_WGI_2025 = (
    "https://www.worldbank.org/content/dam/sites/govindicators/doc/"
    "The%20Worldwide%20Governance%20Indicators%202025%20Methodology%20Revision.pdf"
)
URL_WDI = "https://datatopics.worldbank.org/world-development-indicators/"
URL_WB_API = "https://datahelpdesk.worldbank.org/knowledgebase/articles/889392"
URL_IMF_WEO = "https://www.imf.org/external/datamapper"
URL_UNHCR = "https://www.unhcr.org/refugee-statistics/"
URL_UNHCR_API = "https://api.unhcr.org/docs/refugee-statistics.html"
URL_UCDP = "https://ucdp.uu.se/"
URL_GDELT = "https://www.gdeltproject.org/"

# ---------------------------------------------------------------------------
# Raw series fetched from the APIs.  key -> (provider, code, options)
# provider: "WB" (World Bank API), "IMF" (IMF DataMapper API), "UNHCR"
# ---------------------------------------------------------------------------
WGI_DIMENSIONS = {
    "va": "Voice & Accountability",
    "pv": "Political Stability & Absence of Violence",
    "ge": "Government Effectiveness",
    "rq": "Regulatory Quality",
    "rl": "Rule of Law",
    "cc": "Control of Corruption",
}

RAW_SERIES: dict[str, tuple[str, str, dict]] = {
    # World Bank Worldwide Governance Indicators (source 3), 0-100 score, higher = better
    **{
        f"wgi_{d}": ("WB", f"GOV_WGI_{d.upper()}.SC", {"source": 3})
        for d in WGI_DIMENSIONS
    },
    # World Development Indicators (source 2)
    "pop": ("WB", "SP.POP.TOTL", {}),
    "battle_deaths": ("WB", "VC.BTL.DETH", {}),
    "homicide": ("WB", "VC.IHR.PSRC.P5", {}),
    "reserves_months": ("WB", "FI.RES.TOTL.MO", {}),
    "unemployment": ("WB", "SL.UEM.TOTL.ZS", {}),
    "youth_unemployment": ("WB", "SL.UEM.1524.ZS", {}),
    # IMF World Economic Outlook via DataMapper (includes projections)
    "inflation": ("IMF", "PCPIPCH", {}),
    "gdp_growth": ("IMF", "NGDP_RPCH", {}),
    "gov_debt": ("IMF", "GGXWDG_NGDP", {}),
    "fiscal_balance": ("IMF", "GGXCNL_NGDP", {}),
    "current_account": ("IMF", "BCA_NGDPD", {}),
    "unemployment_imf": ("IMF", "LUR", {}),
    "gdppc": ("IMF", "NGDPDPC", {}),
    "pop_imf": ("IMF", "LP", {}),  # millions; fallback for economies outside the WDI
    # UNHCR: refugees + asylum seekers + other people in need of protection + IDPs, by origin
    "displaced": ("UNHCR", "population", {}),
}

# Confidence-interval series for the WGI charts (loaded lazily on the country page)
WGI_CI_SERIES: dict[str, tuple[str, str, dict]] = {
    **{f"wgi_{d}_lb": ("WB", f"GOV_WGI_{d.upper()}.SC_LB", {"source": 3}) for d in WGI_DIMENSIONS},
    **{f"wgi_{d}_ub": ("WB", f"GOV_WGI_{d.upper()}.SC_UB", {"source": 3}) for d in WGI_DIMENSIONS},
}

SOURCE_LABELS = {
    "WB": "World Bank",
    "IMF": "IMF World Economic Outlook",
    "UNHCR": "UNHCR Refugee Data Finder",
}


# ---------------------------------------------------------------------------
# Pillars and indicators
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Pillar:
    key: str
    label: str
    short: str
    default_weight: int
    question: str


PILLARS: list[Pillar] = [
    Pillar(
        "stability",
        "Political Stability & Violence",
        "Stability",
        35,
        "How likely is political violence, unrest or armed conflict to disrupt people and operations?",
    ),
    Pillar(
        "governance",
        "Governance & Institutions",
        "Governance",
        25,
        "Can institutions be relied on — courts, regulators, contracts, clean administration?",
    ),
    Pillar(
        "economic",
        "Macroeconomic & Financial",
        "Economy",
        25,
        "Is the economy exposed to a crisis — inflation, debt distress, balance-of-payments stress?",
    ),
    Pillar(
        "social",
        "Social & Humanitarian Pressure",
        "Social",
        15,
        "Are there social pressures that can turn into instability — joblessness, displacement?",
    ),
]
PILLAR_BY_KEY = {p.key: p for p in PILLARS}


@dataclass(frozen=True)
class Indicator:
    key: str
    label: str
    short: str
    pillar: str
    higher_is_riskier: bool
    unit: str
    decimals: int
    source: str
    source_url: str
    description: str
    series: str | None = None  # key in RAW_SERIES (None for derived indicators)
    fallback_series: str | None = None  # used where the main series has no value
    lookback: int = 5  # years to look back for the most recent value
    norm: str = "percentile"  # "percentile" or "log" (for zero-heavy indicators)
    scored: bool = True

    def fmt(self, value) -> str:
        if value is None or value != value:  # NaN check
            return "—"
        return f"{value:,.{self.decimals}f}"


INDICATORS: list[Indicator] = [
    # --- Political stability & violence ---------------------------------
    Indicator(
        "wgi_pv", "Political stability & absence of violence", "Political stability",
        "stability", False, "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "Perceptions of the likelihood of political instability and politically motivated "
        "violence, including terrorism. Higher score = more stable.",
        series="wgi_pv", lookback=3,
    ),
    Indicator(
        "battle_deaths_100k", "Battle-related deaths per 100,000 people", "Battle deaths /100k",
        "stability", True, "deaths per 100k", 2, "UCDP via World Bank WDI", URL_UCDP,
        "Deaths in state-based armed conflicts (UCDP definition), scaled by population. "
        "Countries with no recorded conflict are scored 0.",
        norm="log",
    ),
    Indicator(
        "homicide", "Intentional homicides per 100,000 people", "Homicide rate",
        "stability", True, "per 100k", 1, "UNODC via World Bank WDI", URL_WDI,
        "A proxy for criminal violence and the state's control over security.",
        series="homicide", lookback=8,
    ),
    # --- Governance & institutions --------------------------------------
    Indicator(
        "wgi_va", "Voice & accountability", "Voice & accountability", "governance", False,
        "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "Citizens' ability to choose their government; freedom of expression, association and media.",
        series="wgi_va", lookback=3,
    ),
    Indicator(
        "wgi_ge", "Government effectiveness", "Gov. effectiveness", "governance", False,
        "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "Quality of public services and the civil service, and the credibility of policy commitments.",
        series="wgi_ge", lookback=3,
    ),
    Indicator(
        "wgi_rq", "Regulatory quality", "Regulatory quality", "governance", False,
        "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "Ability to formulate and implement sound policies that permit private-sector development.",
        series="wgi_rq", lookback=3,
    ),
    Indicator(
        "wgi_rl", "Rule of law", "Rule of law", "governance", False,
        "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "Confidence in contract enforcement, property rights, the police and the courts.",
        series="wgi_rl", lookback=3,
    ),
    Indicator(
        "wgi_cc", "Control of corruption", "Control of corruption", "governance", False,
        "WGI score, 0–100", 1, "World Bank WGI", URL_WGI,
        "The extent to which public power is exercised for private gain, including state capture.",
        series="wgi_cc", lookback=3,
    ),
    # --- Macroeconomic & financial ----------------------------------------
    Indicator(
        "inflation", "Inflation, average consumer prices", "Inflation",
        "economic", True, "% change", 1, "IMF WEO", URL_IMF_WEO,
        "Current-year IMF estimate. High inflation erodes incomes and is a classic trigger of unrest.",
        series="inflation", lookback=2,
    ),
    Indicator(
        "gdp_growth", "Real GDP growth", "GDP growth", "economic", False,
        "% change", 1, "IMF WEO", URL_IMF_WEO,
        "Current-year IMF estimate. Recessions strain budgets, jobs and political support.",
        series="gdp_growth", lookback=2,
    ),
    Indicator(
        "gov_debt", "General government gross debt", "Public debt", "economic", True,
        "% of GDP", 1, "IMF WEO", URL_IMF_WEO,
        "Current-year IMF estimate. High debt limits room to respond to shocks.",
        series="gov_debt", lookback=2,
    ),
    Indicator(
        "fiscal_balance", "Government net lending/borrowing", "Fiscal balance", "economic", False,
        "% of GDP", 1, "IMF WEO", URL_IMF_WEO,
        "Current-year IMF estimate. Large deficits signal pressure for austerity or money printing.",
        series="fiscal_balance", lookback=2,
    ),
    Indicator(
        "current_account", "Current account balance", "Current account", "economic", False,
        "% of GDP", 1, "IMF WEO", URL_IMF_WEO,
        "Current-year IMF estimate. Persistent deficits create dependence on foreign financing.",
        series="current_account", lookback=2,
    ),
    Indicator(
        "reserves_months", "Total reserves in months of imports", "FX reserves", "economic", False,
        "months of imports", 1, "World Bank WDI", URL_WDI,
        "The buffer against a currency or balance-of-payments crisis. Under 3 months is a common warning line.",
        series="reserves_months", lookback=4,
    ),
    # --- Social & humanitarian pressure ------------------------------------
    Indicator(
        "unemployment", "Unemployment rate", "Unemployment", "social", True,
        "% of labour force", 1, "ILO modelled estimate via World Bank WDI", URL_WDI,
        "Share of the labour force without work (IMF estimate used where the ILO series is missing).",
        series="unemployment", fallback_series="unemployment_imf", lookback=3,
    ),
    Indicator(
        "youth_unemployment", "Youth unemployment (ages 15–24)", "Youth unemployment", "social", True,
        "% of youth labour force", 1, "ILO modelled estimate via World Bank WDI", URL_WDI,
        "A well-documented driver of protest movements.",
        series="youth_unemployment", lookback=3,
    ),
    Indicator(
        "displaced_share", "Forcibly displaced people from the country", "Displaced (% pop.)",
        "social", True, "% of population", 2, "UNHCR", URL_UNHCR,
        "Refugees, asylum seekers, others in need of international protection and internally "
        "displaced people originating from the country, as a share of its population.",
        norm="log",
    ),
]
INDICATOR_BY_KEY = {i.key: i for i in INDICATORS}
SCORED_INDICATORS = [i for i in INDICATORS if i.scored]


def indicators_for(pillar_key: str) -> list[Indicator]:
    return [i for i in SCORED_INDICATORS if i.pillar == pillar_key]


# A pillar is scored only if at least this share of its indicators is available
PILLAR_MIN_SHARE = 0.5
# The composite is scored only if at least this many pillars are available
COMPOSITE_MIN_PILLARS = 3
# For log-normalised indicators: values at or above this percentile of non-zero
# values get the maximum score, so one extreme case does not flatten everyone else
LOG_CAP_QUANTILE = 0.90

# ---------------------------------------------------------------------------
# Risk tiers (ordinal ramp validated for contrast and step visibility)
# ---------------------------------------------------------------------------
# The app uses a black theme, so every ramp runs dark -> bright: low risk recedes into the
# background and high risk glows. Ramps hold one hue in OKLCH with even lightness steps.
@dataclass(frozen=True)
class Tier:
    label: str
    lower: float
    color: str
    text_on: str  # readable text colour on top of the tier colour


TIERS: list[Tier] = [
    Tier("Low", 0, "#9b0e1b", "#ffffff"),
    Tier("Moderate", 20, "#c42d31", "#ffffff"),
    Tier("Elevated", 40, "#e94f4d", "#000000"),
    Tier("High", 60, "#fd8078", "#000000"),
    Tier("Severe", 80, "#feb5ae", "#000000"),
]
TIER_ORDER = [t.label for t in TIERS]
TIER_COLORS = {t.label: t.color for t in TIERS}

# Continuous scale for maps: near-zero recedes toward the black surface, then the tier ramp
MAP_COLORSCALE = [
    [0.0, "#4f0007"],
    [0.2, "#9b0e1b"],
    [0.4, "#c42d31"],
    [0.6, "#e94f4d"],
    [0.8, "#fd8078"],
    [1.0, "#feb5ae"],
]
NO_DATA_COLOR = "#2e2e2c"
OCEAN_COLOR = "#07111f"

# Pillar identity colours (categorical slots 1-4 in fixed order, dark-mode steps) and a one-hue
# map ramp per pillar (OKLCH lightness 0.27 -> 0.87), so brighter always means riskier.
PILLAR_COLORS = {"stability": "#3987e5", "governance": "#d95926", "economic": "#199e70", "social": "#c98500"}
PILLAR_RAMPS = {
    "stability": ["#002550", "#014387", "#1665bc", "#3c89e8", "#74b1fe", "#b9d7fe"],
    "governance": ["#461300", "#772601", "#ad3b01", "#dc5c29", "#fc8a61", "#fec5b1"],
    "economic": ["#012f1e", "#035238", "#047954", "#1fa173", "#5ac698", "#93eac1"],
    "social": ["#372101", "#5f3d03", "#8a5b04", "#b87b0c", "#e19f3f", "#feca85"],
}


# Diverging scale for change maps (dark mode): two hues with a neutral grey midpoint, equal steps per arm,
# matched lightness on both sides (bright = big move, dark grey = no change)
CHANGE_COLORSCALE = [[0.0, "#74b1fe"], [0.25, "#1665bc"], [0.5, "#383835"], [0.75, "#c42d31"], [1.0, "#fd8078"]]


def reversed_scale(scale: list[list]) -> list[list]:
    """The same colours, bright end first (e.g. 'sooner = brighter' for days until an event)."""
    return [[round(1 - t, 4), c] for t, c in reversed(scale)]


def map_colorscale(metric: str) -> list[list]:
    """Composite uses the tier ramp; each pillar map uses its own hue."""
    ramp = PILLAR_RAMPS.get(metric)
    if ramp is None:
        return MAP_COLORSCALE
    return [[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)]


# News search terms for each World Bank region (the full names make poor search queries)
REGION_NEWS = {
    "East Asia & Pacific": '("East Asia" OR "Southeast Asia" OR Pacific)',
    "Europe & Central Asia": '(Europe OR "Central Asia" OR Balkans OR Caucasus)',
    "Latin America & Caribbean": '("Latin America" OR Caribbean OR "South America")',
    "Middle East, North Africa, Afghanistan & Pakistan": '("Middle East" OR "North Africa" OR Gulf OR Afghanistan OR Pakistan)',
    "North America": '("United States" OR Canada)',
    "South Asia": '("South Asia" OR India OR Bangladesh OR "Sri Lanka" OR Nepal)',
    "Sub-Saharan Africa": '(Africa OR Sahel OR "Horn of Africa")',
}

# Rough region centres (lon, lat) for pointing the globe view
REGION_CENTERS = {
    "East Asia & Pacific": (120, 10),
    "Europe & Central Asia": (40, 50),
    "Latin America & Caribbean": (-70, -12),
    "Middle East, North Africa, Afghanistan & Pakistan": (40, 28),
    "North America": (-100, 45),
    "South Asia": (78, 22),
    "Sub-Saharan Africa": (20, -3),
}

# Categorical colours for comparing countries (fixed order, never cycled; dark-mode steps)
SERIES_COLORS = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]
MAX_COMPARE = len(SERIES_COLORS)
PRIMARY = "#3987e5"
FORECAST_GREY = "#898781"
MONO_FONT = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# ---------------------------------------------------------------------------
# Red flags: absolute thresholds shown alongside the relative index
# ---------------------------------------------------------------------------
# (indicator key, comparison, threshold, severity, label)
RED_FLAGS: list[tuple[str, str, float, str, str]] = [
    ("battle_deaths_raw", ">=", 1000, "critical", "War-level violence (≥1,000 battle deaths in a year, UCDP threshold)"),
    ("battle_deaths_raw", ">=", 25, "serious", "Active armed conflict (≥25 battle deaths in a year, UCDP threshold)"),
    ("inflation", ">=", 50, "critical", "Very high inflation (≥50%)"),
    ("inflation", ">=", 20, "serious", "High inflation (≥20%)"),
    ("gdp_growth", "<", 0, "serious", "Economy contracting (negative real GDP growth)"),
    ("gov_debt", ">=", 90, "warning", "High public debt (≥90% of GDP)"),
    ("fiscal_balance", "<=", -5, "warning", "Large fiscal deficit (≥5% of GDP)"),
    ("current_account", "<=", -5, "warning", "Large current-account deficit (≥5% of GDP)"),
    ("reserves_months", "<", 3, "serious", "Thin FX reserves (<3 months of imports)"),
    ("youth_unemployment", ">=", 25, "warning", "Very high youth unemployment (≥25%)"),
    ("displaced_share", ">=", 5, "serious", "Mass displacement (≥5% of population displaced)"),
    ("homicide", ">=", 20, "serious", "Very high homicide rate (≥20 per 100k)"),
]
SEVERITY_ORDER = {"critical": 0, "serious": 1, "warning": 2}
SEVERITY_ICON = {"critical": "🔴", "serious": "🟠", "warning": "🟡"}
SEVERITY_LABEL = {"critical": "Critical", "serious": "Serious", "warning": "Watch"}

# A WGI change is flagged as deteriorating when the score falls by at least this much over 3 years
WGI_TREND_YEARS = 3
WGI_TREND_THRESHOLD = 5.0

# ICD 203 estimative language (Intelligence Community Directive 203, Analytic Standards)
ESTIMATIVE_LANGUAGE: list[tuple[str, str, int, int]] = [
    ("almost no chance", "remote", 1, 5),
    ("very unlikely", "highly improbable", 5, 20),
    ("unlikely", "improbable", 20, 45),
    ("roughly even chance", "roughly even odds", 45, 55),
    ("likely", "probable", 55, 80),
    ("very likely", "highly probable", 80, 95),
    ("almost certain", "nearly certain", 95, 99),
]


def estimative_term(probability: float) -> str:
    """Map a probability (0-100) to the ICD 203 estimative term."""
    for term, _alt, low, high in ESTIMATIVE_LANGUAGE:
        if probability <= high:
            return term
    return ESTIMATIVE_LANGUAGE[-1][0]


# ---------------------------------------------------------------------------
# Country names and extra economies
# ---------------------------------------------------------------------------
# Economies the World Bank country list omits but WGI/IMF cover
EXTRA_ECONOMIES = {
    "TWN": {"name": "Taiwan", "region": "East Asia & Pacific", "income": "High income", "iso2": "TW",
            "capital": "Taipei", "lat": 25.0330, "lng": 121.5654},
}

# Flags: SVGs from the flag-icons package on jsDelivr, pinned to an exact version
FLAG_URL = "https://cdn.jsdelivr.net/npm/flag-icons@7.5.0/flags/4x3/{code}.svg"
NO_FLAG = {"JG"}  # World Bank codes with no flag in the set (Channel Islands)


def flag_url(iso2) -> str | None:
    code = str(iso2 or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or code in NO_FLAG:
        return None
    return FLAG_URL.format(code=code.lower())


# First year of the risk-over-time history (the index is recomputed for every year since)
HISTORY_START = 2015
# WGI rows for non-member economies come without an ISO3 code; map them by name
WB_NAME_TO_ISO3 = {"Taiwan, China": "TWN"}
# IMF codes that differ from World Bank codes
IMF_TO_WB_ISO3 = {"UVK": "XKX", "WBG": "PSE"}

# Plain-English display names (the World Bank uses formal names such as "Egypt, Arab Rep.")
DISPLAY_NAMES = {
    "BHS": "The Bahamas", "BRN": "Brunei", "CIV": "Côte d'Ivoire", "COD": "DR Congo",
    "COG": "Republic of the Congo", "CPV": "Cabo Verde", "CZE": "Czechia", "EGY": "Egypt",
    "FSM": "Micronesia", "GMB": "The Gambia", "HKG": "Hong Kong", "IRN": "Iran",
    "KGZ": "Kyrgyzstan", "KNA": "St Kitts and Nevis", "KOR": "South Korea", "LAO": "Laos",
    "LCA": "St Lucia", "MAC": "Macao", "MKD": "North Macedonia", "PRK": "North Korea",
    "PSE": "West Bank and Gaza", "RUS": "Russia", "SVK": "Slovakia", "SOM": "Somalia", "STP": "São Tomé and Príncipe",
    "SYR": "Syria", "TUR": "Türkiye", "VCT": "St Vincent and the Grenadines", "VEN": "Venezuela",
    "VNM": "Vietnam", "YEM": "Yemen", "TWN": "Taiwan", "VIR": "US Virgin Islands",
    "MAF": "St Martin (French part)", "SXM": "Sint Maarten", "TCA": "Turks and Caicos Islands",
}
# Names that work better as news search terms
NEWS_NAMES = {
    "CIV": "Ivory Coast", "COD": "DR Congo", "COG": "Republic of Congo",
    "PSE": "Palestinian", "TUR": "Turkey", "STP": "Sao Tome", "MKD": "North Macedonia",
}
