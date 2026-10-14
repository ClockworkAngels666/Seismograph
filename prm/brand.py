"""Seismograph brand assets: the mark, the wordmark and the banner wave (SVGs in assets/)."""

from __future__ import annotations

import base64
from functools import cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@cache
def svg(name: str) -> str:
    """The SVG markup of assets/<name>.svg (icon, logo or wave)."""
    return (ASSETS / f"{name}.svg").read_text(encoding="utf-8")


@cache
def data_uri(name: str) -> str:
    """The SVG as a data: URI, for <img> tags in HTML."""
    return "data:image/svg+xml;base64," + base64.b64encode(svg(name).encode("utf-8")).decode("ascii")
