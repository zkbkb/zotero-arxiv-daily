"""Tests for the Bark notifier: endpoint normalization, markdown rendering, payload."""

import pytest
from omegaconf import open_dict

from tests.canned_responses import make_sample_paper, make_stub_requests_post
from zotero_arxiv_daily.digest import Digest
from zotero_arxiv_daily.notifier.bark import (
    BarkNotifier,
    normalize_bark_endpoint,
    render_markdown_body,
)


# ---------------------------------------------------------------------------
# normalize_bark_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("n3tyojo5nCXSzDTdAY5rff", "https://api.day.app/n3tyojo5nCXSzDTdAY5rff"),
        ("https://api.day.app/mykey", "https://api.day.app/mykey"),
        ("https://api.day.app/mykey/", "https://api.day.app/mykey"),
        ("https://api.day.app/mykey/标题/正文", "https://api.day.app/mykey"),
        ("api.day.app/mykey", "https://api.day.app/mykey"),
        ("http://push.example.com:8080/mykey/extra", "http://push.example.com:8080/mykey"),
        ("  mykey  ", "https://api.day.app/mykey"),
    ],
)
def test_normalize_bark_endpoint(raw, expected):
    assert normalize_bark_endpoint(raw) == expected


# ---------------------------------------------------------------------------
# render_markdown_body
# ---------------------------------------------------------------------------


def _make_papers(n):
    return [
        make_sample_paper(
            title=f"Paper {i}",
            url=f"https://arxiv.org/abs/2026.0000{i}",
            tldr=f"TLDR of paper {i}.",
            score=9.0 - i,
        )
        for i in range(n)
    ]


def test_render_markdown_body_contains_intro_links_scores_and_stars():
    papers = _make_papers(3)
    digest = Digest(title="t", intro="Read the first one.", highlight_indices=[0])
    body = render_markdown_body(papers, digest, max_chars=3000)

    assert body.startswith("Read the first one.")
    assert "1. ⭐ [Paper 0](https://arxiv.org/abs/2026.00000) `9.0`" in body
    assert "2. [Paper 1](https://arxiv.org/abs/2026.00001) `8.0`" in body
    assert "TLDR of paper 0." in body
    assert body.count("⭐") == 1


def test_render_markdown_body_collapses_multiline_tldr():
    papers = [make_sample_paper(tldr="line one\nline two", score=5.0)]
    digest = Digest(title="t", intro="", highlight_indices=[])
    body = render_markdown_body(papers, digest, max_chars=3000)
    assert "line one line two" in body


def test_render_markdown_body_truncates_whole_entries():
    papers = _make_papers(10)
    digest = Digest(title="t", intro="Intro here.", highlight_indices=[])
    max_chars = 400
    body = render_markdown_body(papers, digest, max_chars=max_chars)

    assert len(body) <= max_chars
    assert "Intro here." in body
    assert "more papers not shown_" in body
    # entries are dropped from the tail, so the first paper survives
    assert "[Paper 0](https://arxiv.org/abs/2026.00000)" in body
    assert "[Paper 9]" not in body


# ---------------------------------------------------------------------------
# BarkNotifier
# ---------------------------------------------------------------------------


def _make_bark_notifier(config, monkeypatch, calls, endpoint="fakekey", status_code=200, **bark_overrides):
    with open_dict(config):
        config.notifier.bark.endpoint = endpoint
        for key, value in bark_overrides.items():
            config.notifier.bark[key] = value
    monkeypatch.setattr(
        "zotero_arxiv_daily.notifier.bark.requests.post",
        make_stub_requests_post(calls, status_code=status_code),
    )
    return BarkNotifier(config)


def test_bark_notifier_requires_endpoint(config):
    assert config.notifier.bark.endpoint is None
    with pytest.raises(ValueError, match="endpoint is required"):
        BarkNotifier(config)


def test_bark_notifier_sends_payload(config, monkeypatch):
    calls = []
    notifier = _make_bark_notifier(config, monkeypatch, calls)
    papers = _make_papers(2)
    digest = Digest(title="今日AI大爆发", intro="Read paper 0.", highlight_indices=[0])

    notifier.notify(papers, digest)

    assert len(calls) == 1
    call = calls[0]
    assert call.url == "https://api.day.app/fakekey"
    assert call.timeout == 10
    assert call.headers == {"Content-Type": "application/json; charset=utf-8"}
    payload = call.json
    assert payload["title"] == "今日AI大爆发"
    assert payload["body"] == "Read paper 0."
    assert "⭐ [Paper 0]" in payload["markdown"]
    assert payload["group"] == "arXiv"
    assert payload["sound"] == "calypso"
    assert payload["level"] == "active"
    assert payload["isArchive"] == "1"
    assert "url" not in payload
    assert "icon" not in payload


def test_bark_notifier_includes_optional_fields_when_configured(config, monkeypatch):
    calls = []
    notifier = _make_bark_notifier(
        config,
        monkeypatch,
        calls,
        icon="https://example.com/icon.png",
        click_url="https://example.com",
    )
    digest = Digest(title="t", intro="", highlight_indices=[])

    notifier.notify(_make_papers(1), digest)

    payload = calls[0].json
    assert payload["icon"] == "https://example.com/icon.png"
    assert payload["url"] == "https://example.com"


def test_bark_notifier_empty_papers_sends_minimal_push(config, monkeypatch):
    calls = []
    notifier = _make_bark_notifier(config, monkeypatch, calls)
    digest = Digest(title="No new papers today (2026-07-15)", intro="", highlight_indices=[], is_fallback=True)

    notifier.notify([], digest)

    payload = calls[0].json
    assert payload["title"] == "No new papers today (2026-07-15)"
    assert payload["body"] == "No new papers today"
    assert "markdown" not in payload


def test_bark_notifier_uses_fallback_digest_when_digest_is_none(config, monkeypatch):
    calls = []
    notifier = _make_bark_notifier(config, monkeypatch, calls)

    notifier.notify(_make_papers(2), digest=None)

    payload = calls[0].json
    assert "2 papers" in payload["title"]


def test_bark_notifier_raises_on_http_error(config, monkeypatch):
    calls = []
    notifier = _make_bark_notifier(config, monkeypatch, calls, status_code=500)
    digest = Digest(title="t", intro="", highlight_indices=[])

    with pytest.raises(RuntimeError, match="HTTP 500"):
        notifier.notify(_make_papers(1), digest)
