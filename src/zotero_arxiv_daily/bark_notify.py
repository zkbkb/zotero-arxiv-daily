"""Optional Bark delivery path, independent from email."""

from __future__ import annotations

from loguru import logger
from openai import OpenAI
from omegaconf import DictConfig, OmegaConf

from .construct_bark import render_bark_markdown
from .daily_brief import fallback_daily_brief, generate_daily_brief
from .protocol import Paper
from .utils import is_bark_enabled, send_bark


def deliver_bark(config: DictConfig, papers: list[Paper], openai_client: OpenAI) -> None:
    """Generate brief + markdown and push to Bark when enabled.

    Errors are logged and swallowed so email delivery remains independent.
    """
    if not is_bark_enabled(config):
        return

    if not papers and not OmegaConf.select(config, "bark.send_empty", default=False):
        logger.info("No papers for Bark and bark.send_empty=false; skipping Bark push.")
        return

    try:
        max_n = int(OmegaConf.select(config, "bark.max_paper_num", default=10) or 10)
        bark_papers = papers[:max_n] if max_n > 0 else []
        if bark_papers:
            brief = generate_daily_brief(bark_papers, openai_client, config.llm)
        else:
            brief = fallback_daily_brief([])
        markdown = render_bark_markdown(bark_papers, brief)
        logger.info(f"Sending Bark notification: {brief.title}")
        send_bark(config, brief.title, markdown)
        logger.info("Bark notification sent successfully")
    except Exception as e:
        logger.warning(f"Bark notification failed (email path unaffected): {e}")
