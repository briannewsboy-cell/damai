import logging
from datetime import datetime
from urllib.parse import urljoin

import pytz
import requests

from checkers.base import ConcertResult
from config import Config
from retry import with_retry

logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Shanghai")

# Retry config for Damai search/detail requests (spec: 3 retries, exp backoff).
RETRIES = 3
BACKOFF_BASE = 1.0
# Retry on network errors and HTTP errors (4xx/5xx). Timeouts are a subclass
# of RequestException so they're covered.
RETRY_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
)


class HttpDamaiChecker:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

    def check(self) -> ConcertResult:
        search_url = "https://search.damai.cn/searchajax.html"
        params = {
            "keyword": self.config.concert_keyword,
            "cty": "苏州",
        }
        response = self._get_with_retry(search_url, params=params)
        data = response.json()

        items = data.get("data", {}).get("list", [])
        if not items:
            # Empty results are a valid "not on sale" signal, not an error.
            # Returning here keeps the GitHub Actions job green and lets the
            # normal state-persistence path run.
            logger.warning(
                "No search results found for keyword=%r; reporting not_on_sale",
                self.config.concert_keyword,
            )
            return ConcertResult(
                title="",
                url="",
                status="not_on_sale",
                on_sale=False,
                checked_at=datetime.now(TZ).isoformat(),
            )

        item = self._pick_best_item(items)
        detail_url = urljoin("https://detail.damai.cn/", item.get("url", ""))
        title = item.get("name", "")

        detail_response = self._get_with_retry(detail_url)
        on_sale = self._parse_sale_status(detail_response.text)

        return ConcertResult(
            title=title,
            url=detail_url,
            status="on_sale" if on_sale else "not_on_sale",
            on_sale=on_sale,
            checked_at=datetime.now(TZ).isoformat(),
        )

    def _get_with_retry(self, url: str, **kwargs) -> requests.Response:
        """GET ``url`` with 3 retries and exponential backoff.

        ``raise_for_status`` runs inside the retry so transient 5xx responses
        are retried rather than failing the check immediately.
        """

        def do() -> requests.Response:
            resp = self.session.get(url, timeout=10, **kwargs)
            resp.raise_for_status()
            return resp

        return with_retry(
            do,
            retries=RETRIES,
            backoff_base=BACKOFF_BASE,
            exceptions=RETRY_EXCEPTIONS,
            label=f"GET {url}",
        )

    def _pick_best_item(self, items: list[dict]) -> dict:
        keyword = self.config.concert_keyword.replace(" ", "")
        best = items[0]
        best_score = 0
        for item in items:
            name = item.get("name", "")
            city = item.get("cityname", "")
            score = sum(1 for term in keyword if term in name)
            if "苏州" in city:
                score += 10
            if score > best_score:
                best_score = score
                best = item
        return best

    def _parse_sale_status(self, html: str) -> bool:
        sale_phrases = ["立即购买", "购票", "选座购买", "马上预订"]
        return any(phrase in html for phrase in sale_phrases)
