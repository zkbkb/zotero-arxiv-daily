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
    labels = {
        "lead": "今日导读" if chinese else "Today at a glance",
        "reason": "推荐理由" if chinese else "Why it matters",
        "summary": "核心内容" if chinese else "In one sentence",
        "relevance": "相关度" if chinese else "Relevance",
        "paper": "论文页面" if chinese else "Paper",
        "pdf": "PDF",
        "empty": "今天没有发现新论文，休息一下吧。" if chinese else "No papers today. Take a rest!",
    }

    parts: list[str] = []
    if brief.brief:
        parts.append(
            f"> **{labels['lead']}**\n>\n"
            f"> {brief.brief.strip()}"
        )

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
        lines = [f"### {len(paper_sections) + 1}. {paper.title}"]
        if highlight.comment:
            lines.append(f"**{labels['reason']}**\n\n{highlight.comment}")
        summary = (highlight.summary or paper.tldr or "").strip()
        if summary:
            lines.append(f"**{labels['summary']}**\n\n{summary}")

        metadata = f"`{labels['relevance']} {_format_score(paper.score)}`"
        if paper.url and paper.pdf_url and paper.url != paper.pdf_url:
            metadata += (
                f" · [{labels['paper']}]({paper.url})"
                f" · [{labels['pdf']}]({paper.pdf_url})"
            )
        else:
            metadata += f" · [{labels['paper']}]({_paper_link(paper)})"
        lines.append(metadata)
        paper_sections.append("\n\n".join(lines))

    if paper_sections:
        parts.extend(paper_sections)

    if not parts:
        return labels["empty"]

    return "\n\n---\n\n".join(parts).strip()
