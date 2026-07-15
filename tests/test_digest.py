"""Tests for zotero_arxiv_daily.digest: generate_digest, fallback_digest."""

from types import SimpleNamespace

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.digest import fallback_digest, generate_digest


def _stub_client(content: str):
    def create(**kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


def _papers():
    return [
        make_sample_paper(title="Paper A", tldr="TLDR A", score=8.0),
        make_sample_paper(title="Paper B", tldr="TLDR B", score=7.0),
        make_sample_paper(title="Paper C", tldr="TLDR C", score=6.0),
    ]


def test_generate_digest_parses_response_and_converts_to_zero_based():
    client = _stub_client('{"title": "Big News", "intro": "Papers A and B matter.", "highlights": [1, 2]}')
    digest = generate_digest(_papers(), client, {"language": "English"})

    assert digest.title == "Big News"
    assert digest.intro == "Papers A and B matter."
    assert digest.highlight_indices == [0, 1]
    assert digest.is_fallback is False


def test_generate_digest_parses_json_wrapped_in_prose_or_code_fence():
    client = _stub_client('Here you go:\n```json\n{"title": "T", "intro": "I", "highlights": [3]}\n```')
    digest = generate_digest(_papers(), client, {"language": "English"})

    assert digest.title == "T"
    assert digest.highlight_indices == [2]


def test_generate_digest_dedupes_and_clamps_highlights():
    client = _stub_client('{"title": "T", "intro": "I", "highlights": [1, 1, 99, 0, 2]}')
    digest = generate_digest(_papers(), client, {"language": "English"})

    # 1-based: 1->0, 1->0 (dup, dropped), 99 out of range (dropped),
    # 0 -> -1 out of range (dropped), 2 -> 1
    assert digest.highlight_indices == [0, 1]


def test_generate_digest_caps_highlights_at_three():
    client = _stub_client('{"title": "T", "intro": "I", "highlights": [1, 2, 3]}')
    papers = _papers() + [make_sample_paper(title="Paper D", tldr="TLDR D", score=5.0)]
    digest = generate_digest(papers, client, {"language": "English"})
    assert len(digest.highlight_indices) <= 3


def test_generate_digest_falls_back_on_malformed_json():
    client = _stub_client("not json at all")
    digest = generate_digest(_papers(), client, {"language": "English"})

    assert digest.is_fallback is True
    assert "3" in digest.title


def test_generate_digest_falls_back_on_client_exception():
    def create(**kwargs):
        raise RuntimeError("boom")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    digest = generate_digest(_papers(), client, {"language": "English"})

    assert digest.is_fallback is True


def test_generate_digest_falls_back_on_empty_title():
    client = _stub_client('{"title": "", "intro": "I", "highlights": []}')
    digest = generate_digest(_papers(), client, {"language": "English"})

    assert digest.is_fallback is True


def test_generate_digest_empty_papers_returns_fallback_without_llm_call():
    def create(**kwargs):
        raise AssertionError("LLM should not be called for an empty paper list")

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    digest = generate_digest([], client, {"language": "English"})

    assert digest.is_fallback is True
    assert digest.highlight_indices == []


def test_fallback_digest_language_chinese():
    digest = fallback_digest(_papers(), "Chinese")
    assert "今日" in digest.title
    assert "3" in digest.title


def test_fallback_digest_language_english():
    digest = fallback_digest(_papers(), "English")
    assert "Daily arXiv Digest" in digest.title


def test_fallback_digest_empty_papers():
    digest = fallback_digest([], "English")
    assert "No new papers" in digest.title
