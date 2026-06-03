"""
Stage 6: Report Assembly

Renders ClusterSummary objects to a dated markdown digest file.
"""

from __future__ import annotations

import re
from datetime import date as date_type
from pathlib import Path

from pipeline.types import ClusterSummary

MISC_ID = -1


def build_report(summaries: list[ClusterSummary], date: str) -> str:
    """
    Render summaries to a markdown string.

    Args:
        summaries: Output of Summarizer.summarize_all() — sorted by total_importance,
                   Miscellaneous last.
        date:      ISO date string, e.g. "2026-03-13".

    Returns:
        Markdown string ready to write to disk.
    """
    lines: list[str] = []
    lines.append(f"# Daily Digest — {date}\n")

    for s in summaries:
        is_misc = s["id"] == MISC_ID
        header = f"## {s['label']}  ({s['tweet_count']} tweets)"
        lines.append(header)

        if is_misc:
            lines.append("*(no summary)*\n")
            lines.append("---\n")
            continue

        if s.get("summary"):
            lines.append(s["summary"] + "\n")

        for b in s.get("bullets", []):
            source_links = " ".join(f"[↗]({url})" for url in b.get("urls", []))
            bullet_line = f"- {b['text']}"
            if source_links:
                bullet_line += f"  {source_links}"
            lines.append(bullet_line)

        lines.append("")
        lines.append("---\n")

    return "\n".join(lines)


def write_report(
    summaries: list[ClusterSummary],
    date: str | None = None,
    out_dir: str | Path = "digests",
) -> Path:
    """
    Build and write the markdown report to disk.

    Args:
        summaries: Output of Summarizer.summarize_all().
        date:      ISO date string. Defaults to today.
        out_dir:   Directory to write into. Created if it doesn't exist.

    Returns:
        Path to the written file.
    """
    if date is None:
        date = str(date_type.today())

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"daily_digest_{date}.md"
    out_path = out_dir / filename

    content = build_report(summaries, date)
    out_path.write_text(content, encoding="utf-8")
    print(f"  Report written to {out_path}")
    return out_path
