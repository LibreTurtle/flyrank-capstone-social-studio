from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PublishResult:
    remote_reference: str
    preview: str


class PublishFailure(Exception):
    def __init__(self, message: str, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


class SocialPublisher(Protocol):
    name: str

    def publish(self, *, text: str, idempotency_key: str) -> PublishResult: ...
