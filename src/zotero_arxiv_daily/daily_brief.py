"""Generate an attractive daily push title and brief from reranked papers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime

from loguru import logger
from openai import OpenAI
from omegaconf import DictConfig

from .protocol import Paper


@dataclass
class Highlight:
    index: int
    comment: str = ""


@dataclass
class DailyBrief:
    title: str
    brief: str
    highlights: list[Highlight] = field(default_factory=list)


def fallback_daily_brief(papers: list[Paper], today: str | None = None) -> DailyBrief:
    date_str = today or datetime.now().strftime("%Y/%m/%d")
    highlights = [Highlight(index=i) for i in range(len(papers))]
    return DailyBrief(
        title=f"Daily arXiv {date_str}",
        brief="",
        highlights=highlights,
    )


def _extract_json_object(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _parse_daily_brief(payload: dict, paper_count: int) -> DailyBrief:
    title = str(payload.get("title") or "").strip()
    brief = str(payload.get("brief") or "").strip()
    raw_highlights = payload.get("highlights") or []
    highlights: list[Highlight] = []
    if isinstance(raw_highlights, list):
        for item in raw_highlights:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index"))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= paper_count:
                continue
            comment = str(item.get("comment") or "").strip()
            highlights.append(Highlight(index=index, comment=comment))
    if not title:
        raise ValueError("daily brief title is empty")
    if not highlights:
        highlights = [Highlight(index=i) for i in range(paper_count)]
    return DailyBrief(title=title, brief=brief, highlights=highlights)


def generate_daily_brief(
    papers: list[Paper],
    openai_client: OpenAI,
    llm_params: DictConfig | dict,
) -> DailyBrief:
    """Ask the LLM for a catchy title, short brief, and worth-reading highlights."""
    if not papers:
        return fallback_daily_brief([])

    lang = llm_params.get("language", "English")
    paper_lines = []
    for i, paper in enumerate(papers):
        score = round(paper.score, 2) if paper.score is not None else "Unknown"
        tldr = (paper.tldr or paper.abstract or "").strip()
        paper_lines.append(
            f"[{i}] score={score}\n"
            f"title: {paper.title}\n"
            f"tldr: {tldr}"
        )
    papers_block = "\n\n".join(paper_lines)

    system = (
        f"You write catchy mobile push-notification titles and short daily briefs "
        f"for a research-paper digest. Always answer in {lang}. "
        f"Return ONLY a JSON object, no markdown fences."
    )
    user = (
        "Given today's ranked papers (higher score = more relevant to the reader's library), "
        "select the papers that are most worth reading, then write:\n"
        "- title: one short, attention-grabbing push title that captures today's theme "
        "(not a bland date-only subject line)\n"
        "- brief: 1-3 sentences of editorial lead-in highlighting why they matter\n"
        "- highlights: a JSON array of objects {\"index\": <int>, \"comment\": \"<one-line remark>\"} "
        "for the papers worth reading (use the bracketed index). Prefer relevance + substance; "
        "skip weak or redundant items when reasonable.\n\n"
        f"Papers:\n{papers_block}\n\n"
        "Example shape:\n"
        '{"title":"...", "brief":"...", "highlights":[{"index":0,"comment":"..."}]}'
    )

    try:
        response = openai_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **llm_params.get("generation_kwargs", {}),
        )
        content = response.choices[0].message.content or ""
        payload = _extract_json_object(content)
        return _parse_daily_brief(payload, len(papers))
    except Exception as e:
        logger.warning(f"Failed to generate daily brief, using fallback: {e}")
        return fallback_daily_brief(papers)
