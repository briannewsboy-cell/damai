from datetime import datetime, timezone
from urllib.parse import urljoin

import requests

from config import Config
from checkers.base import ConcertResult


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
        response = self.session.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        items = data.get("data", {}).get("list", [])
        if not items:
            raise RuntimeError("No search results found")

        item = self._pick_best_item(items)
        detail_url = urljoin("https://detail.damai.cn/", item.get("url", ""))
        title = item.get("name", "")

        detail_response = self.session.get(detail_url, timeout=10)
        detail_response.raise_for_status()
        on_sale = self._parse_sale_status(detail_response.text)

        return ConcertResult(
            title=title,
            url=detail_url,
            status="on_sale" if on_sale else "not_on_sale",
            on_sale=on_sale,
            checked_at=datetime.now(timezone.utc).isoformat(),
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
