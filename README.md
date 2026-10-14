<img src="assets/logo.svg" alt="Seismograph" width="380">

# Seismograph

**Picking up political tremors before they become earthquakes.** A transparent country-risk index built from open
data, with an analyst's judgment on top.

🔗 **Live app:** https://YOUR-APP-NAME.streamlit.app  *(replace after deploying)*

Seismograph scores around 200 economies on political, governance, economic and social risk using live data from the
World Bank, IMF, UNHCR and the Uppsala Conflict Data Program. It follows the structure professional country-risk
models use — indicators → pillars → a weighted composite — and shows every step, so a reader can see *why* a
country scores the way it does and challenge the assumptions.

On top of the model sit the parts a model cannot do: **red flags** on absolute thresholds, a **live news pulse**,
an **events watchlist**, and **written analyst assessments** with probabilistic key judgments and scenarios.

## What you can do in the app

| Page | What it shows |
|---|---|
| **Global overview** | Interactive 3D globe — rotate, zoom, click any country (small states are dots) to see its index and **its latest news**, replay the index year by year since 2015, pulsing rings where armed conflict is active, animated refugee-flow arcs — or a flat map; headline numbers with sparklines and year-on-year changes; risk matrix, tier distribution by region, sortable ranking with flags and 1-year change arrows, biggest movers in political stability |
| **Country profile** | Composite score and rank (with trend and change vs last year), automatic data brief, red flags, pillar scores vs regional median, **risk over time** since 2015, sensitivity check, a **what-if simulator** (move indicator sliders or pick a scenario such as *currency crisis* or *armed conflict* and watch the score, tier and rank update), every indicator with its year and source, WGI trends with confidence intervals, IMF macro charts with projections, live risk-related headlines, and the analyst assessment |
| **Compare countries** | Up to six countries — add them from any profile with *Add to compare*: pillar radar, governance over time, indicator table, economic trajectories |
| **Events watchlist** | Elections, deadlines and other dated events on a timeline |
| **Live TV & video** | 25 round-the-clock live news channels from five regions (Europe, the Americas, the Middle East, Africa and Asia-Pacific), each labelled with where it is based and who owns it, plus the latest video reports, think-tank analysis (CFR, Crisis Group, Carnegie, Brookings, Atlantic Council, CSIS) and briefings from institutions and NGOs (UN, IMF, World Bank, ICRC, Human Rights Watch), filterable by country; each profile also shows the videos about that country |
| **Real-world guide** | What the numbers mean in real life: a plain-language reading of any country, what each tier, pillar and warning threshold looks like on the ground, practical steps for business, NGOs, travel and research, and the tool's limits. Each country profile also has an *In real life* tab with the same reading |
| **What changed** | This year vs last: biggest risers and fallers, tier changes, the pillar that drove each move, red flags newly crossed or cleared |
| **Regional briefings** | One region at a time: headline numbers with trends, zoomed map, tier mix since 2015, risers and fallers, ranking, upcoming events and regional news |
| **Conflict & displacement** | Battle deaths worldwide and by conflict, a table of active wars and conflicts, displacement over time, largest origin and host countries, and the 25 largest refugee corridors |
| **Economic stress** | A heatmap of inflation, growth, debt, deficits, current account and reserves, a growth-vs-inflation (stagflation) chart, the IMF outlook, and countries crossing several warning thresholds |
| **Indicator explorer** | Any of the 17 indicators on the 3D globe, with its distribution and the riskiest and safest 10 countries |
| **Assessment builder** | A form that turns your analysis into a structured assessment file (BLUF, key judgments with ICD 203 estimative language, drivers, scenarios, signposts) |
| **Methodology** | Every indicator, normalisation, weight, threshold and limitation |
| **Glossary & legend** | 106 terms in nine colour-coded categories, each with its icon and the sources behind it, searchable; every term links to the organisation that defines or publishes it; plus a visual legend for tiers, pillars, colour scales and globe layers |
| **Sources & citations** | Every dataset, definition and feed behind the tool, with links, update dates and the status of the data loaded now; the source of every warning threshold; independent indices to cross-check the scores against; who owns each video channel; and how to cite the tool |
| **Resources** | Curated data sources, professional outlooks, tradecraft guides and books |

Most pages open on their own **3D globe**: the overview (with a live news column and hotspots to watch), regional
briefings (turned to the region), conflict & displacement (conflict rings and refugee arcs), economic stress, a
diverging *map of change* on *What changed*, the compared countries on *Compare*, upcoming events on the
watchlist, and each country's own refugee links on its profile. Every chart, map and table names its sources
underneath, with links.

A **console bar** along the bottom of every page keeps the tracked country one tap away (flag, score, tier,
change and a small seismogram of its risk since 2015) next to tabs for Home, Compare, Live and Guide and a
*Find* sheet for countries and pages.

## Method in brief

* **17 indicators in 4 pillars**: Political Stability & Violence (35%), Governance & Institutions (25%),
  Macroeconomic & Financial (25%), Social & Humanitarian Pressure (15%). Weights are adjustable in the app.
* **Normalisation**: percentile ranks (0 = lowest risk in the sample, 100 = highest); battle deaths and
  displacement use a capped log scale so that "no conflict" scores zero.
* **Aggregation**: arithmetic mean within pillars, weighted mean across pillars, with minimum-data rules.
* **Robustness**: sensitivity check on every profile; WGI changes tested against 90% confidence intervals.
* **Red flags**: absolute thresholds (e.g. UCDP's 25 battle-death threshold for armed conflict, reserves below
  three months of imports) to complement the relative index.

Full details are on the in-app *Methodology* page; the logic lives in [`prm/scoring.py`](prm/scoring.py) and every
indicator, weight and threshold is defined in [`prm/config.py`](prm/config.py).

## Data sources

| Source | Used for | Access |
|---|---|---|
| [World Bank Worldwide Governance Indicators](https://www.worldbank.org/en/publication/worldwide-governance-indicators) | Six governance dimensions (2025 methodology, 0–100 scores) | Public API |
| [World Bank World Development Indicators](https://datatopics.worldbank.org/world-development-indicators/) | Population, battle deaths (UCDP), homicides, reserves, unemployment | Public API |
| [IMF World Economic Outlook](https://www.imf.org/external/datamapper) | Growth, inflation, debt, fiscal and current-account balances, projections | Public API |
| [UNHCR Refugee Data Finder](https://www.unhcr.org/refugee-statistics/) | Forcibly displaced people by origin | Public API |
| [Bing News](https://www.bing.com/news) and [Google News](https://news.google.com/) (RSS search) | Live risk-related headlines with photos, refreshed every 10 minutes | Public feeds |
| [GDELT Project](https://www.gdeltproject.org/) | Backup news source and media tone | Public API |
| [IFES ElectionGuide](https://www.electionguide.org/) | Dates for the events watchlist | Website |

Pages open instantly from the snapshot in `data/snapshot/` (refreshed monthly by a GitHub Action) while the
live data downloads in the background; live data is then kept for 12 hours, and any source that is down keeps
its snapshot copy. The risk-over-time view recomputes the index for every year since 2015 with the data
available for that year. The 3D globe draws [Natural Earth](https://www.naturalearthdata.com/)
country outlines (public domain) with [globe.gl](https://globe.gl/).

## Project structure

```
streamlit_app.py          entry point and navigation
app_pages/                one file per page
prm/config.py             indicators, pillars, weights, tiers, thresholds
prm/sources.py            API clients (World Bank, IMF, UNHCR, GDELT)
prm/scoring.py            normalisation, aggregation, red flags, automatic brief
prm/charts.py             Plotly charts
prm/globe.py              interactive 3D globe (custom Streamlit component)
prm/data.py               caching and snapshot fallback
assessments/              analyst assessments, one Markdown file per country
data/events.csv           events watchlist
scripts/refresh_snapshot.py  saves an offline copy of all data
```

## Run it yourself

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Deployment on Streamlit Community Cloud is described step by step in [DEPLOY.md](DEPLOY.md).

## Limitations

The index is relative and largely backward-looking: governance data describe the previous year and conflict data
lag by up to a year. Governance indicators are perception-based and carry margins of error. Countries with the
least data are often those with the most risk. The score is a structured starting point for analysis, not a
forecast — which is why the assessments exist.

## Author

**Tuan Dung Nguyen** — International Relations student.

Research design, indicator selection and all country assessments are my own.

## Licence

Code: MIT (see [LICENSE](LICENSE)). Data remain subject to each provider's terms; please cite the original sources.
