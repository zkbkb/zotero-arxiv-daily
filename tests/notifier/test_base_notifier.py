"""Tests for the notifier registry."""

import pytest

from zotero_arxiv_daily.notifier import get_notifier_cls, registered_notifiers
from zotero_arxiv_daily.notifier.base import BaseNotifier, register_notifier


def test_register_notifier_registers_class_and_sets_name():
    @register_notifier("dummy-test-notifier")
    class DummyNotifier(BaseNotifier):
        def notify(self, papers, digest=None):
            pass

    try:
        assert DummyNotifier.name == "dummy-test-notifier"
        assert get_notifier_cls("dummy-test-notifier") is DummyNotifier
    finally:
        del registered_notifiers["dummy-test-notifier"]


def test_get_notifier_cls_unknown_name_raises():
    with pytest.raises(ValueError, match="Notifier nope not found"):
        get_notifier_cls("nope")


def test_builtin_notifiers_are_registered():
    assert "email" in registered_notifiers
    assert "bark" in registered_notifiers


def test_email_notifier_does_not_need_digest_and_bark_does():
    assert get_notifier_cls("email").needs_digest is False
    assert get_notifier_cls("bark").needs_digest is True
