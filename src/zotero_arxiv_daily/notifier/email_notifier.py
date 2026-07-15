from typing import Optional

from ..construct_email import render_email
from ..digest import Digest
from ..protocol import Paper
from ..utils import send_email
from .base import BaseNotifier, register_notifier


@register_notifier("email")
class EmailNotifier(BaseNotifier):
    def notify(self, papers: list[Paper], digest: Optional[Digest] = None) -> None:
        html = render_email(papers)
        send_email(self.config, html)
