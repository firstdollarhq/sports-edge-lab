"""Appends dated markdown entries to journal/. The journal is the honesty
mechanism for this project: every run should record what happened, not just
the wins. See README.md 'Journal discipline'."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

JOURNAL_DIR = Path(__file__).parents[3] / "journal"


def _slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def new_entry(title: str, sections: dict[str, str], entry_date: date | None = None) -> Path:
    entry_date = entry_date or date.today()
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    path = JOURNAL_DIR / f"{entry_date.isoformat()}-{_slugify(title)}.md"

    lines = [f"# {title}", "", f"_{entry_date.isoformat()}_", ""]
    for heading, body in sections.items():
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(body.strip())
        lines.append("")

    path.write_text("\n".join(lines))
    return path
