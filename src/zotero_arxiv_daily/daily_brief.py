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
    headline: str = ""
    insight: str = ""


@dataclass
class DailyBrief:
    title: str
    subtitle: str = ""
    highlights: list[Highlight] = field(default_factory=list)


def fallback_daily_brief(papers: list[Paper], today: str | None = None) -> DailyBrief:
    date_str = today or datetime.now().strftime("%Y/%m/%d")
    highlights = [Highlight(index=i) for i in range(len(papers))]
    return DailyBrief(
        title=f"Daily arXiv {date_str}",
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
    subtitle = str(payload.get("subtitle") or "").strip()
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
            headline = str(item.get("headline") or "").strip()
            insight = str(item.get("insight") or "").strip()
            highlights.append(
                Highlight(index=index, headline=headline, insight=insight)
            )
    if not title:
        raise ValueError("daily brief title is empty")
    if not highlights:
        highlights = [Highlight(index=i) for i in range(paper_count)]
    return DailyBrief(title=title, subtitle=subtitle, highlights=highlights)


def generate_daily_brief(
    papers: list[Paper],
    openai_client: OpenAI,
    llm_params: DictConfig | dict,
    language: str | None = None,
) -> DailyBrief:
    """Ask the LLM for a polished title, brief, and worth-reading highlights."""
    if not papers:
        return fallback_daily_brief([])

    lang = language or llm_params.get("language", "English")
    paper_lines = []
    for i, paper in enumerate(papers):
        score = round(paper.score, 2) if paper.score is not None else "Unknown"
        tldr = (paper.tldr or paper.abstract or "").strip()
        abstract = (paper.abstract or "").strip()[:2000]
        paper_lines.append(
            f"[{i}] score={score}\n"
            f"title: {paper.title}\n"
            f"tldr: {tldr}\n"
            f"abstract: {abstract}"
        )
    papers_block = "\n\n".join(paper_lines)

    system = (
        "You are a curious, knowledgeable friend sharing a fascinating research find "
        "in a mobile message—not an academic reviewer writing a report. "
        f"Always answer in {lang}. Sound natural, vivid, and conversational while staying accurate. "
        "Create genuine curiosity without clickbait, hype, slogans, or marketing clichés. "
        "Every sentence must communicate a concrete research idea, result, mechanism, "
        "trade-off, or implication. Never spend words describing the digest itself, "
        "how many papers it contains, or that papers are worth reading. "
        "Avoid stiff phrases such as 'this paper proposes', 'the study demonstrates', "
        "'focuses on', 'framework', 'core content', and 'worthy of attention'. "
        "Keep original paper titles unchanged. "
        "Never invent a number, benchmark result, method name, or comparison that is not "
        "explicitly supported by the supplied title, TLDR, or abstract. "
        "Return ONLY a JSON object, no markdown fences."
    )
    user = (
        "Given today's ranked papers (higher score = more relevant to the reader's library), "
        "first identify the single most surprising, delightful, counter-intuitive, or "
        "practically useful insight in the material. It may come from only one paper; "
        "do not try to summarize the collection as a whole. Then write:\n"
        "- title: state that concrete insight directly in one short, curiosity-provoking sentence. "
        "Do not prefix it with 'Today', 'Daily', 'Must-read', 'Paper digest', or similar framing. "
        "Do not describe or summarize the batch, mention multiple themes, or use framing like "
        "'five ideas'. It is fine—and preferred—to focus entirely on the strongest story. "
        "Aim for no more than 25 Chinese characters or 12 English words when practical\n"
        "- subtitle: one vivid, information-dense sentence that makes the title more concrete "
        "by adding its key mechanism, number, or consequence. It is the notification's native "
        "subtitle, not an overview. Never repeat or paraphrase the title, mention the batch, "
        "paper count, or say what is 'worth reading'\n"
        "- highlights: a JSON array of objects "
        "{\"index\": <int>, \"headline\": \"<paper-specific editorial headline>\", "
        "\"insight\": \"<one concise, vivid takeaway>\"} "
        "for the selected papers (use the bracketed index). Put the paper that supports the "
        "title first. Prefer relevance + substance and skip weak or redundant items. "
        "Write each headline as a concrete tension, question, unexpected result, or vivid "
        "comparison—not the original academic title and not a generic topic label. "
        "Every item gets its own headline, including the first one. Each headline must name "
        "a recognizable method, model, dataset, or idea from that paper so the academic title "
        "does not need to be displayed in full. The first item's headline must take a clearly "
        "different angle from both the push title and subtitle—never rephrase or repeat them. "
        "The reading experience is tiered, so vary the depth: the FIRST item is the lead "
        "story—give it the richest insight (2-3 sentences with the key mechanism and result). "
        "The next one or two items get a 1-2 sentence insight. Any remaining items form a "
        "quick-scan list: their headline alone must carry the hook, and their insight should "
        "be empty or a single short clause. "
        "Prefer specific methods, numbers, and outcomes when they are present in the input. "
        "Do not label the text as a recommendation or summary.\n\n"
        f"Papers:\n{papers_block}\n\n"
        "Example shape:\n"
        '{"title":"...", "subtitle":"...", "highlights":['
        '{"index":0,"headline":"...","insight":"..."}]}'
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
