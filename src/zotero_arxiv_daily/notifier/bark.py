from typing import Optional
from urllib.parse import urlparse

import requests
from loguru import logger
from omegaconf import DictConfig

from ..digest import Digest, fallback_digest
from ..protocol import Paper
from .base import BaseNotifier, register_notifier

DEFAULT_BARK_SERVER = "https://api.day.app"


def _has_http_scheme(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _looks_like_url(value: str) -> bool:
    if _has_http_scheme(value):
        return True
    head = value.split("/", 1)[0]
    return "." in head or ":" in head


def normalize_bark_endpoint(raw: str) -> str:
    """Normalize a device key or push URL to a POST base endpoint.

    Accepts a bare device key, a full URL (optionally with GET-style
    /title/body path segments, which are stripped), or a host/key form
    without a scheme.
    """
    value = str(raw).strip()
    if not _looks_like_url(value):
        return f"{DEFAULT_BARK_SERVER}/{value.strip('/')}"
    if not _has_http_scheme(value):
        value = f"https://{value}"
    parsed = urlparse(value)
    if not parsed.netloc:
        return value.rstrip("/")
    scheme = (parsed.scheme or "https").lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return f"{scheme}://{parsed.netloc}"
    device_key = path_parts[0]
    return f"{scheme}://{parsed.netloc}/{device_key}"


def _format_score(paper: Paper) -> str:
    return f" (`{paper.score:.1f}`)" if paper.score is not None else ""


def _format_highlight_block(index: int, paper: Paper, highlight) -> str:
    return (
        f"## {index}. {highlight.headline}\n"
        f"- [{paper.title}{_format_score(paper)}]({paper.url})\n"
        f"- {highlight.blurb}"
    )


def _format_roundup_line(index: int, paper: Paper) -> str:
    tldr = " ".join((paper.tldr or paper.abstract or "").split())
    line = f"- {index}. [{paper.title}]({paper.url}){_format_score(paper)}"
    if tldr:
        line += f" — {tldr}"
    return line


def render_markdown_body(papers: list[Paper], digest: Digest, max_chars: int) -> str:
    """Render the digest as markdown: expanded highlight sections for the
    must-read papers, followed by a compact roundup of the rest. Truncates
    the roundup (and, if still too long, the highlights) from the tail --
    never mid-entry -- until the body fits max_chars."""
    intro = digest.intro.strip()
    highlight_by_index = {h.index: h for h in digest.highlights}

    highlight_blocks = [
        _format_highlight_block(idx + 1, papers[idx], highlight_by_index[idx])
        for idx in sorted(highlight_by_index)
    ]
    roundup_lines = [
        _format_roundup_line(i + 1, p)
        for i, p in enumerate(papers)
        if i not in highlight_by_index
    ]

    def assemble(kept_highlights: list[str], kept_roundup: list[str]) -> str:
        parts = []
        if intro:
            parts.append(intro)
        parts.extend(kept_highlights)
        if kept_roundup or len(kept_roundup) < len(roundup_lines):
            section = "其余速览\n" + "\n".join(kept_roundup)
            if len(kept_roundup) < len(roundup_lines):
                section += f"\n_+{len(roundup_lines) - len(kept_roundup)} more papers not shown_"
            parts.append(section)
        return "\n\n".join(parts)

    kept_highlights = list(highlight_blocks)
    kept_roundup = list(roundup_lines)
    while kept_roundup and len(assemble(kept_highlights, kept_roundup)) > max_chars:
        kept_roundup.pop()
    while len(kept_highlights) > 1 and len(assemble(kept_highlights, kept_roundup)) > max_chars:
        kept_highlights.pop()
    return assemble(kept_highlights, kept_roundup)


@register_notifier("bark")
class BarkNotifier(BaseNotifier):
    needs_digest = True

    def __init__(self, config: DictConfig):
        super().__init__(config)
        bark_config = config.notifier.bark
        if not bark_config.endpoint:
            raise ValueError(
                "config.notifier.bark.endpoint is required when 'bark' is in "
                "executor.notifiers. Set it to your Bark device key or push URL "
                "(e.g. via the BARK_ENDPOINT environment variable)."
            )
        self.endpoint = normalize_bark_endpoint(str(bark_config.endpoint))
        self.sound = bark_config.sound
        self.group = bark_config.group
        self.level = bark_config.level
        self.is_archive = int(bark_config.is_archive)
        self.icon = bark_config.icon
        self.click_url = bark_config.click_url
        self.max_body_chars = int(bark_config.max_body_chars)

    def notify(self, papers: list[Paper], digest: Optional[Digest] = None) -> None:
        if digest is None:
            digest = fallback_digest(papers, self.config.llm.get("language", "English"))
        if papers:
            markdown_body = render_markdown_body(papers, digest, self.max_body_chars)
            plain_body = digest.intro.strip() or f"{len(papers)} new papers today"
        else:
            # empty day: minimal push, no paper list
            markdown_body = None
            plain_body = digest.intro.strip() or "No new papers today"

        payload = {
            "title": digest.title,
            # plain-text fallback for Bark clients without markdown support;
            # markdown-capable clients ignore body when markdown is present
            "body": plain_body,
            "group": self.group,
            "sound": self.sound,
            "level": self.level,
            "isArchive": str(self.is_archive),
        }
        if markdown_body:
            payload["markdown"] = markdown_body
        if self.click_url:
            payload["url"] = self.click_url
        if self.icon:
            payload["icon"] = self.icon

        response = requests.post(
            self.endpoint,
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=10,
        )
        response.raise_for_status()
        logger.info(f"Bark push sent: {digest.title}")
