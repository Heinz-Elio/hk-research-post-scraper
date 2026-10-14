"""
Auto-register career-page scrapers.

A source module is any .py file in this package that is not named base
and does not start with _. It must define KEY and scrape().
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict, List

SCRAPERS: Dict[str, Callable[[], List[dict]]] = {}
SOURCE_NAMES: Dict[str, str] = {}


def _register_modules() -> None:
    package = __name__
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_") or info.name == "base":
            continue
        mod = importlib.import_module(f"{package}.{info.name}")
        key = getattr(mod, "KEY", None)
        scrape_fn = getattr(mod, "scrape", None)
        if not key or not callable(scrape_fn):
            continue
        SCRAPERS[key] = scrape_fn
        SOURCE_NAMES[key] = getattr(mod, "NAME", key)


_register_modules()
