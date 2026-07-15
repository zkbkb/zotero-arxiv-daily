"""Render Bark markdown body from a daily brief and paper list."""

from __future__ import annotations

from .daily_brief import DailyBrief, Highlight
from .protocol import Paper


def _format_score(score: float | None) -> str:
    if score is None:
        return "—"
    return str(round(score, 1))


def _uses_chinese(language: str) -> bool:
    normalized = language.strip().lower()
    return normalized.startswith(("zh", "chinese", "中文", "汉语", "漢語"))


def render_bark_markdown(
    papers: list[Paper],
    brief: DailyBrief,
    *,
    include_all_if_no_highlights: bool = True,
    language: str = "Chinese",
) -> str:
    """Build markdown content for Bark (title is sent separately)."""
    chinese = _uses_chinese(language)
    empty_message = (
        "今天没有发现新论文，休息一下吧。"
        if chinese
        else "No papers today. Take a rest!"
    )

    parts: list[str] = []
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
        number = len(paper_sections) + 1
        score = _format_score(paper.score)
        paper_link = f"[{paper.title} ({score})]({paper.url})"
        lines: list[str] = []
        if highlight.headline:
            lines.append(f"### {number}. {highlight.headline}")
            lines.append(paper_link)
        else:
            lines.append(f"### {number}. {paper_link}")

        insight = (highlight.insight or paper.tldr or "").strip()
        if insight:
            lines.append(insight)
        paper_sections.append("\n\n".join(lines))

    if paper_sections:
        parts.extend(paper_sections)

    if not parts:
        return empty_message

    return "\n\n".join(parts).strip()
