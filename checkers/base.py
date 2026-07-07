from dataclasses import dataclass
from typing import Protocol


@dataclass
class ConcertResult:
    title: str
    url: str
    status: str  # "not_on_sale" | "on_sale"
    on_sale: bool
    checked_at: str


class DamaiChecker(Protocol):
    def check(self) -> ConcertResult:
        ...
