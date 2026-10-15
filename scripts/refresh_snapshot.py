"""Save a copy of every data series to data/snapshot/ so the app still works if an API is down.

Run it yourself with:   python scripts/refresh_snapshot.py
or let the GitHub Action in .github/workflows/refresh-data.yml run it once a month.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from prm import config, data, sources  # noqa: E402

OUT = ROOT / "data" / "snapshot"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    meta_path = OUT / "meta.json"
    old_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta = {"created": dt.date.today().isoformat(), "series": dict(old_meta.get("series", {}))}

    try:
        sources.fetch_wb_countries().to_csv(OUT / "countries.csv", index=False)
        print("countries: ok")
    except sources.SourceError as exc:
        print(f"countries: FAILED — {exc} (keeping previous file)")

    try:
        flows = sources.fetch_unhcr_flows()
        flows.to_csv(OUT / "flows.csv", index=False)
        print(f"flows: {len(flows)} origin-host pairs ({int(flows['year'].max())})")
    except sources.SourceError as exc:
        print(f"flows: FAILED — {exc} (keeping previous file)")

    results = sources.fetch_many({**config.RAW_SERIES, **config.WGI_CI_SERIES})
    failed = []
    for key, res in sorted(results.items()):
        if res.error or res.data.empty:
            failed.append(key)
            print(f"{key}: FAILED — {res.error} (keeping previous file)")
            continue
        res.data.to_csv(OUT / f"{key}.csv", index=False)
        meta["series"][key] = {
            "provider": res.provider,
            "code": res.code,
            "last_updated": res.last_updated,
            "edition": res.edition,
            "rows": int(len(res.data)),
            "saved": meta["created"],
        }
        print(f"{key}: {len(res.data)} rows")

    # The index for every year with the default weights, so the app's first page opens without computing it
    try:
        series = {key: pd.read_csv(OUT / f"{key}.csv") for key in config.RAW_SERIES if (OUT / f"{key}.csv").exists()}
        countries = pd.read_csv(OUT / "countries.csv")
        for col in ("iso2", "lat", "lng"):
            if col not in countries.columns:
                countries[col] = None
        history = data.build_default_history(series, countries)
        history.to_csv(OUT / "history.csv", index=False)
        print(f"history: {len(history)} country-years")
    except Exception as exc:  # the app rebuilds it if this fails
        print(f"history: FAILED — {exc}")

    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"\nDone. {len(results) - len(failed)} of {len(results)} series saved.")
    return 1 if len(failed) == len(results) else 0


if __name__ == "__main__":
    sys.exit(main())
