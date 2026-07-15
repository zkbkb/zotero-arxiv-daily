from abc import ABC, abstractmethod
from typing import Optional, Type

from omegaconf import DictConfig

from ..digest import Digest
from ..protocol import Paper


class BaseNotifier(ABC):
    name: str
    needs_digest: bool = False

    def __init__(self, config: DictConfig):
        self.config = config

    @abstractmethod
    def notify(self, papers: list[Paper], digest: Optional[Digest] = None) -> None:
        pass


registered_notifiers = {}


def register_notifier(name: str):
    def decorator(cls):
        registered_notifiers[name] = cls
        cls.name = name
        return cls
    return decorator


def get_notifier_cls(name: str) -> Type[BaseNotifier]:
    if name not in registered_notifiers:
        raise ValueError(f"Notifier {name} not found")
    return registered_notifiers[name]
