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


class DamaiBlockedError(RuntimeError):
    """Raised when Damai returns an anti-bot/CAPTCHA page instead of data."""


NOT_SALE_PHRASES = ["预售", "即将开售", "缺货登记", "预约抢票"]
SALE_PHRASES = ["立即购买", "选座购买", "马上预订"]


def parse_sale_status(html: str, detail_mode: bool = False) -> bool:
    """Infer sale status from a Damai detail page.

    Args:
        html: The page HTML.
        detail_mode: Kept for backwards compatibility; the logic is now the same
            for both search and direct-detail flows.

    Returns:
        True only when the page contains explicit on-sale button text and no
        pre-sale/out-of-stock markers.
    """
    if any(phrase in html for phrase in NOT_SALE_PHRASES):
        return False
    return any(phrase in html for phrase in SALE_PHRASES)


def parse_detail_sale_status(html: str) -> bool:
    """Convenience wrapper for checking a specific detail URL."""
    return parse_sale_status(html, detail_mode=True)