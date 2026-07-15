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


# Tiered layout: 1 lead story, then short featured items, then a quick-scan list.
_FEATURED_COUNT = 2


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
    more_label = "其余速览" if chinese else "Also new"

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

    sections: list[str] = []
    bullets: list[str] = []
    for position, (highlight, paper) in enumerate(selected):
        score = _format_score(paper.score)
        paper_link = f"[{paper.title} ({score})]({paper.url})"
        insight = (highlight.insight or paper.tldr or "").strip()

        if highlight.headline and position == 0:
            # Lead story: full treatment, mirrors the push title's insight.
            block = f"### {highlight.headline}\n\n{paper_link}"
            if insight:
                block += f"\n\n{insight}"
            sections.append(block)
        elif highlight.headline and position <= _FEATURED_COUNT:
            block = f"**{highlight.headline}**\n\n{paper_link}"
            if insight:
                block += f"\n\n{insight}"
            sections.append(block)
        else:
            hook = highlight.headline or insight
            if hook:
                bullets.append(f"- {paper_link} — {hook}")
            else:
                bullets.append(f"- {paper_link}")

    if bullets:
        bullet_block = "\n".join(bullets)
        if sections:
            sections.append(f"**{more_label}**\n\n{bullet_block}")
        else:
            sections.append(bullet_block)

    if not sections:
        return empty_message

    return "\n\n".join(sections).strip()
