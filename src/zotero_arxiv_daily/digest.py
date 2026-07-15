import json
import re
from dataclasses import dataclass, field
from datetime import datetime

import tiktoken
from loguru import logger
from openai import OpenAI

from .protocol import Paper

MAX_HIGHLIGHTS = 3

_SYSTEM_PROMPT = (
    "You are the editor of a daily arXiv digest push notification. "
    "Respond in {lang}. Return ONLY a JSON object, no other text."
)

_USER_PROMPT_INSTRUCTIONS = """
Produce a JSON object:
{"title": "...", "intro": "...", "highlights": [1, 3]}
- "title": a catchy, attention-grabbing push-notification headline (<=30 characters for Chinese, <=60 for English) capturing the day's dominant theme. Punchy like a viral tech-media headline, but factually accurate -- never fabricate results the papers do not claim.
- "intro": a 2-3 sentence editor's note naming the 1-3 papers most worth reading today and why.
- "highlights": the numbers (1-based) of those must-read papers, at most 3.
"""


@dataclass
class Digest:
    title: str
    intro: str
    highlight_indices: list[int] = field(default_factory=list)  # 0-based
    is_fallback: bool = False


def _is_chinese(language: str) -> bool:
    return "chinese" in language.lower() or "中文" in language


def fallback_digest(papers: list[Paper], language: str) -> Digest:
    today = datetime.now().strftime("%Y-%m-%d")
    if len(papers) == 0:
        title = f"今日无新论文 ({today})" if _is_chinese(language) else f"No new papers today ({today})"
    elif _is_chinese(language):
        title = f"📚 今日 arXiv 精选 {len(papers)} 篇 ({today})"
    else:
        title = f"📚 Daily arXiv Digest: {len(papers)} papers ({today})"
    return Digest(title=title, intro="", highlight_indices=[], is_fallback=True)


def _generate_digest_with_llm(papers: list[Paper], openai_client: OpenAI, llm_params: dict) -> Digest:
    lang = llm_params.get("language", "English")
    lines = []
    for i, p in enumerate(papers, start=1):
        score = f"{p.score:.1f}" if p.score is not None else "N/A"
        tldr = " ".join((p.tldr or p.abstract or "").split())
        lines.append(f"{i}. {p.title} (score {score})\n   TLDR: {tldr}")
    prompt = (
        "Here are today's top recommended papers (numbered, with relevance score and TLDR):\n\n"
        + "\n".join(lines)
        + "\n"
        + _USER_PROMPT_INSTRUCTIONS
    )

    # use gpt-4o tokenizer for estimation
    enc = tiktoken.encoding_for_model("gpt-4o")
    prompt_tokens = enc.encode(prompt)
    prompt_tokens = prompt_tokens[:4000]  # truncate to 4000 tokens
    prompt = enc.decode(prompt_tokens)

    response = openai_client.chat.completions.create(
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT.format(lang=lang)},
            {"role": "user", "content": prompt},
        ],
        **llm_params.get("generation_kwargs", {}),
    )
    content = response.choices[0].message.content
    parsed = json.loads(re.search(r"\{.*\}", content, flags=re.DOTALL).group(0))

    title = str(parsed["title"]).strip()
    if not title:
        raise ValueError("LLM returned an empty digest title")
    intro = str(parsed.get("intro", "")).strip()
    highlight_indices = []
    for h in parsed.get("highlights", []):
        idx = int(h) - 1  # model uses 1-based numbering
        if 0 <= idx < len(papers) and idx not in highlight_indices:
            highlight_indices.append(idx)
    return Digest(title=title, intro=intro, highlight_indices=highlight_indices[:MAX_HIGHLIGHTS])


def generate_digest(papers: list[Paper], openai_client: OpenAI, llm_params: dict) -> Digest:
    language = llm_params.get("language", "English")
    if len(papers) == 0:
        return fallback_digest(papers, language)
    try:
        return _generate_digest_with_llm(papers, openai_client, llm_params)
    except Exception as e:
        logger.warning(f"Failed to generate digest with LLM: {e}")
        return fallback_digest(papers, language)
