"""Load config/leagues.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parents[2] / "config" / "leagues.yaml"


@lru_cache(maxsize=1)
def load(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_PATH).read_text())


def league(name: str) -> dict:
    cfg = load()["leagues"]
    if name not in cfg:
        raise KeyError(f"Unknown league {name!r}; have {sorted(cfg)}")
    return cfg[name]


def is_live_enabled(name: str) -> bool:
    """Whether this league's model is cleared to produce real paper bets."""
    return bool(league(name).get("live_enabled", False))


def liquidity_kwargs() -> dict:
    """Translate config keys into betting.liquidity.check kwargs."""
    liq = load().get("liquidity", {}) or {}
    return {
        "max_spread": liq.get("max_spread", 0.05),
        "min_size": liq.get("min_ask_size", 50),
        "min_volume": liq.get("min_volume", 500),
        "min_price": liq.get("min_price", 0.03),
        "max_price": liq.get("max_price", 0.97),
    }
