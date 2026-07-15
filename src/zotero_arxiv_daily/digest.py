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
    "You are a sharp, witty tech editor who curates a daily arXiv digest that people actually look forward to opening. "
    "You know the research cold, but you write like a great science communicator: vivid, specific, playful, opinionated -- never dry, robotic, or corporate. "
    "Write all content in {lang}. Return ONLY a JSON object, no other text."
)

_USER_PROMPT_INSTRUCTIONS = """
Return a JSON object with this exact shape:
{"title": "...", "intro": "...", "highlights": [{"index": 1, "headline": "...", "blurb": "..."}]}

VOICE (this matters most): write like a top-tier tech blogger / 科技媒体, NOT like a paper abstract. Be punchy, concrete, curious, a little cheeky. Lead with the hook. Use the actual "aha" trick and real numbers from each paper. Have a point of view. But stay strictly truthful: never invent results or exaggerate beyond what the papers claim.

- "title": a scroll-stopping headline for the whole push that frames the day's theme with personality and a hook. BANNED: dry openers like "今日"/"每日"/"Today's"/"Daily", and lifeless templates like "X的三/五种方法/解法" or "关于X的研究". Make someone want to tap it. <=30 characters for Chinese, <=60 for English.
- "intro": ONE lively sentence that sets up why today's picks are worth reading -- voice and framing, not a summary.
- "highlights": the 1-3 papers most worth reading in depth. For each:
  - "index": its 1-based number from the list above.
  - "headline": a curiosity-gap hook -- a provocative question or bold claim capturing the paper's core trick. Example energy: "48GB 显卡硬扛 65B 模型，QLoRA 是怎么做到的？"
  - "blurb": 2-3 vivid sentences explaining the actual mechanism AND the punchline result, with concrete numbers, that make me want to click. Grounded strictly in the paper's TLDR/abstract.
"""


@dataclass
class Highlight:
    index: int  # 0-based
    headline: str
    blurb: str


@dataclass
class Digest:
    title: str
    intro: str
    highlights: list[Highlight] = field(default_factory=list)
    is_fallback: bool = False


def _is_chinese(language: str) -> bool:
    return "chinese" in language.lower() or "中文" in language


def fallback_digest(papers: list[Paper], language: str) -> Digest:
    today = datetime.now().strftime("%Y-%m-%d")
    if len(papers) == 0:
        title = f"今日无新论文 ({today})" if _is_chinese(language) else f"No new papers today ({today})"
    elif _is_chinese(language):
        title = f"📚 arXiv 精选 {len(papers)} 篇 ({today})"
    else:
        title = f"📚 arXiv Digest: {len(papers)} papers ({today})"
    return Digest(title=title, intro="", highlights=[], is_fallback=True)


def _parse_highlights(raw_highlights, num_papers: int) -> list[Highlight]:
    highlights = []
    seen_indices = set()
    for item in raw_highlights:
        idx = int(item["index"]) - 1  # model uses 1-based numbering
        if not (0 <= idx < num_papers) or idx in seen_indices:
            continue
        headline = str(item.get("headline", "")).strip()
        blurb = str(item.get("blurb", "")).strip()
        if not headline:
            continue
        seen_indices.add(idx)
        highlights.append(Highlight(index=idx, headline=headline, blurb=blurb))
        if len(highlights) >= MAX_HIGHLIGHTS:
            break
    return highlights


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
    highlights = _parse_highlights(parsed.get("highlights", []), len(papers))
    return Digest(title=title, intro=intro, highlights=highlights)


def generate_digest(papers: list[Paper], openai_client: OpenAI, llm_params: dict) -> Digest:
    language = llm_params.get("language", "English")
    if len(papers) == 0:
        return fallback_digest(papers, language)
    try:
        return _generate_digest_with_llm(papers, openai_client, llm_params)
    except Exception as e:
        logger.warning(f"Failed to generate digest with LLM: {e}")
        return fallback_digest(papers, language)
