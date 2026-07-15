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
    source_label = "原论文" if chinese else "Paper"
    relevance_label = "相关度" if chinese else "relevance"

    highlights = list(brief.highlights)
    if not highlights and include_all_if_no_highlights:
        highlights = [Highlight(index=i) for i in range(len(papers))]

    selected: list[tuple[Highlight, Paper]] = []
    seen: set[int] = set()
    for highlight in highlights:
        if highlight.index in seen or highlight.index < 0 or highlight.index >= len(papers):
            continue
        seen.add(highlight.index)
        selected.append((highlight, papers[highlight.index]))

    # Every paper is a numbered story: editorial headline, insight, then a
    # compact source link. Long academic titles stay behind the link instead
    # of dominating the mobile screen.
    sections: list[str] = []
    for position, (highlight, paper) in enumerate(selected):
        number = position + 1
        score = _format_score(paper.score)
        paper_link = (
            f"[{source_label} · {relevance_label} {score}]({paper.url})"
        )
        insight = (highlight.insight or paper.tldr or "").strip()

        if highlight.headline:
            block = f"**{number}｜{highlight.headline}**"
        else:
            block = f"**{number}｜{paper.title}**"
        if insight:
            block += f"\n\n{insight}"
        block += f"\n\n{paper_link}"
        sections.append(block)

    if not sections:
        return empty_message

    return "\n\n".join(sections).strip()
