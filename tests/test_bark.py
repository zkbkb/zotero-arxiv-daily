"""Tests for daily brief generation, Bark markdown rendering, and send_bark."""

from types import SimpleNamespace

from omegaconf import open_dict

from tests.canned_responses import make_sample_paper, make_stub_openai_client
from zotero_arxiv_daily.construct_bark import render_bark_markdown
from zotero_arxiv_daily.daily_brief import (
    DailyBrief,
    Highlight,
    fallback_daily_brief,
    generate_daily_brief,
)
from zotero_arxiv_daily.utils import is_bark_enabled, send_bark


def test_fallback_daily_brief_uses_date_title():
    papers = [make_sample_paper(title="A"), make_sample_paper(title="B")]
    brief = fallback_daily_brief(papers, today="2026/07/15")
    assert brief.title == "Daily arXiv 2026/07/15"
    assert brief.brief == ""
    assert [h.index for h in brief.highlights] == [0, 1]


def test_generate_daily_brief_parses_stub_json():
    papers = [
        make_sample_paper(title="Paper A", score=8.5, tldr="TLDR A"),
        make_sample_paper(title="Paper B", score=7.2, tldr="TLDR B"),
    ]
    brief = generate_daily_brief(papers, make_stub_openai_client(), {"language": "English", "generation_kwargs": {}})
    assert "multimodal" in brief.title.lower()
    assert brief.brief
    assert len(brief.highlights) == 2
    assert brief.highlights[0].comment
    assert brief.highlights[0].summary


def test_generate_daily_brief_fallback_on_invalid_json():
    class BrokenClient:
        chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
                )
            )
        )

    papers = [make_sample_paper(title="Only Paper", score=9.0, tldr="x")]
    brief = generate_daily_brief(papers, BrokenClient(), {"language": "English", "generation_kwargs": {}})
    assert brief.title.startswith("Daily arXiv")
    assert [h.index for h in brief.highlights] == [0]


def test_render_bark_markdown_includes_brief_and_highlights():
    papers = [
        make_sample_paper(title="Alpha Paper", score=8.8, tldr="Alpha TLDR", pdf_url="https://example.com/a.pdf"),
        make_sample_paper(title="Beta Paper", score=6.1, tldr="Beta TLDR", pdf_url="https://example.com/b.pdf"),
    ]
    brief = DailyBrief(
        title="Catchy Title",
        brief="Today's focus is Alpha.",
        highlights=[
            Highlight(
                index=0,
                comment="Top pick",
                summary="A clearer summary than the original TLDR.",
            )
        ],
    )
    md = render_bark_markdown(papers, brief, language="Chinese")
    assert "Today's focus is Alpha." in md
    assert "> **今日导读**" in md
    assert "### 1. Alpha Paper" in md
    assert "**推荐理由**\n\nTop pick" in md
    assert "**核心内容**\n\nA clearer summary than the original TLDR." in md
    assert "`相关度 8.8`" in md
    assert "[PDF](https://example.com/a.pdf)" in md
    assert "\n\n---\n\n" in md
    assert "Beta Paper" not in md


def test_render_bark_markdown_empty():
    md = render_bark_markdown([], DailyBrief(title="t", brief="", highlights=[]))
    assert "今天没有发现新论文" in md


def test_is_bark_enabled_requires_flag_and_key(config):
    with open_dict(config):
        config.bark.enabled = False
        config.bark.device_key = "abc"
    assert is_bark_enabled(config) is False

    with open_dict(config):
        config.bark.enabled = True
        config.bark.device_key = None
    assert is_bark_enabled(config) is False

    with open_dict(config):
        config.bark.enabled = "true"
        config.bark.device_key = "  mykey  "
    assert is_bark_enabled(config) is True


def test_send_bark_posts_title_and_markdown(config, monkeypatch):
    captured = {}

    class StubResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"code": 200, "message": "success"}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return StubResponse()

    monkeypatch.setattr("zotero_arxiv_daily.utils.requests.post", fake_post)

    with open_dict(config):
        config.bark.enabled = True
        config.bark.device_key = "device-key"
        config.bark.server = "https://api.day.app"
        config.bark.group = "Arxiv"

    send_bark(config, "Hello Title", "## md body")

    assert captured["url"] == "https://api.day.app/device-key"
    assert captured["json"]["title"] == "Hello Title"
    assert captured["json"]["markdown"] == "## md body"
    assert captured["json"]["group"] == "Arxiv"
    assert "body" not in captured["json"]
