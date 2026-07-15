"""Render Bark markdown body from a daily brief and paper list."""

from __future__ import annotations

from .daily_brief import DailyBrief, Highlight
from .protocol import Paper


def _paper_link(paper: Paper) -> str:
    if paper.pdf_url:
        return paper.pdf_url
    return paper.url


def _format_score(score: float | None) -> str:
    if score is None:
        return "Unknown"
    return str(round(score, 1))


def render_bark_markdown(
    papers: list[Paper],
    brief: DailyBrief,
    *,
    include_all_if_no_highlights: bool = True,
) -> str:
    """Build markdown content for Bark (title is sent separately)."""
    parts: list[str] = []
    if brief.brief:
        parts.append(brief.brief.strip())

    highlights = list(brief.highlights)
    if not highlights and include_all_if_no_highlights:
        highlights = [Highlight(index=i) for i in range(len(papers))]

    paper_sections: list[str] = []
    seen: set[int] = set()
    for highlight in highlights:
        if highlight.index in seen or highlight.index < 0 or highlight.index >= len(papers):
            continue
        seen.add(highlight.index)
        paper = papers[highlight.index]
        lines = [
            f"### {paper.title}",
            f"**Relevance:** {_format_score(paper.score)}",
        ]
        if highlight.comment:
            lines.append(f"**Why:** {highlight.comment}")
        tldr = (paper.tldr or "").strip()
        if tldr:
            lines.append(f"**TLDR:** {tldr}")
        lines.append(f"[PDF]({_paper_link(paper)})")
        if paper.url and paper.pdf_url and paper.url != paper.pdf_url:
            lines.append(f"[Abstract]({paper.url})")
        paper_sections.append("\n".join(lines))

    if paper_sections:
        if parts:
            parts.append("")
        parts.append("## Highlights" if brief.brief else "## Papers")
        parts.extend(paper_sections)

    if not parts:
        return "No Papers Today. Take a Rest!"

    return "\n\n".join(parts).strip()
