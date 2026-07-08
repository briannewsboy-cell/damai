import gzip
import json
import logging
from datetime import datetime
from urllib.parse import urljoin, urlparse

import pytz

from checkers.base import ConcertResult, DamaiBlockedError, parse_detail_sale_status, parse_sale_status
from config import Config

logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Shanghai")

# Markers in a response body that indicate Damai's anti-bot/CAPTCHA challenge.
BLOCKED_MARKERS = ("_____tmd_____", "bxpunish", "captcha", "x5secdata")


class PlaywrightDamaiChecker:
    """Browser-based Damai checker used as a fallback when HTTP requests are blocked.

    Damai's searchajax endpoint returns an anti-bot/CAPTCHA page from many
    cloud/datacenter IPs. A real browser context can sometimes bypass the
    challenge and either expose the JSON response or render the search results
    into the DOM.
    """

    def __init__(self, config: Config):
        self.config = config

    def check(self) -> ConcertResult:
        # Defer the import so the rest of the application can run (and tests can
        # execute) even when Playwright is not installed.
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed; install it with 'pip install playwright'"
            ) from e

        if self.config.concert_detail_url:
            return self._check_detail_page(sync_playwright)
        return self._check_via_search(sync_playwright)

    def _check_detail_page(self, sync_playwright) -> ConcertResult:
        """Check a known detail URL directly using Playwright."""
        detail_url = self.config.concert_detail_url
        logger.info("Checking configured detail URL with Playwright: %s", detail_url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()
            page.goto(detail_url, wait_until="networkidle", timeout=30000)
            detail_html = page.content()
            browser.close()

        on_sale = parse_detail_sale_status(detail_html)
        title = self.config.concert_keyword
        return ConcertResult(
            title=title,
            url=detail_url,
            status="on_sale" if on_sale else "not_on_sale",
            on_sale=on_sale,
            checked_at=self._now_iso(),
        )

    def _check_via_search(self, sync_playwright) -> ConcertResult:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()

            captured: dict = {}

            def is_search_ajax(response) -> bool:
                """Return True only for the real search JSON endpoint.

                Damai's anti-bot flow issues redirect/punish URLs that also
                contain ``searchajax.html`` (e.g. ``/searchajax.html/_____tmd_____/punish``).
                Those must not overwrite a valid captured result.
                """
                if response.request.method != "GET":
                    return False
                parsed = urlparse(response.url)
                return parsed.path == "/searchajax.html"

            def handle_response(response) -> None:
                if not is_search_ajax(response):
                    return
                parsed = self._try_parse_response(response)
                if parsed is None:
                    return
                items = parsed.get("data", {}).get("list", [])
                logger.info(
                    "Intercepted searchajax response with %d item(s)", len(items)
                )
                # Keep the response with the most results. Later CAPTCHA/empty
                # responses must not overwrite an earlier valid result.
                existing_items = captured.get("data", {}).get("list", [])
                if len(items) >= len(existing_items):
                    captured["data"] = parsed

            page.on("response", handle_response)

            search_page_url = (
                f"https://search.damai.cn/search.htm?"
                f"keyword={self.config.concert_keyword}&cty=苏州"
            )
            logger.info("Navigating to Damai search page with Playwright: %s", search_page_url)
            page.goto(search_page_url, wait_until="networkidle", timeout=30000)
            # Allow late responses to fire after networkidle.
            page.wait_for_timeout(2000)

            data = captured.get("data")
            if not data:
                data = self._extract_from_dom(page)

            html = page.content().lower()
            if not data and any(marker in html for marker in BLOCKED_MARKERS):
                raise DamaiBlockedError(
                    "Damai blocked Playwright with an anti-bot/CAPTCHA page"
                )

            browser.close()

        if not data:
            logger.warning("Playwright found no search results; reporting not_on_sale")
            return ConcertResult(
                title="",
                url="",
                status="not_on_sale",
                on_sale=False,
                checked_at=self._now_iso(),
            )

        items = data.get("data", {}).get("list", [])
        if not items:
            logger.warning(
                "Playwright search returned empty list for keyword=%r; reporting not_on_sale",
                self.config.concert_keyword,
            )
            return ConcertResult(
                title="",
                url="",
                status="not_on_sale",
                on_sale=False,
                checked_at=self._now_iso(),
            )

        item = self._pick_best_item(items)
        detail_url = urljoin("https://detail.damai.cn/", item.get("url", ""))
        title = item.get("name", "")

        logger.info("Navigating to detail page with Playwright: %s", detail_url)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()
            page.goto(detail_url, wait_until="networkidle", timeout=30000)
            detail_html = page.content()
            browser.close()

        on_sale = parse_sale_status(detail_html)
        return ConcertResult(
            title=title,
            url=detail_url,
            status="on_sale" if on_sale else "not_on_sale",
            on_sale=on_sale,
            checked_at=self._now_iso(),
        )

    def _extract_from_dom(self, page) -> dict | None:
        """Fallback extraction from rendered DOM when JSON interception misses."""
        try:
            items = page.evaluate(
                """() => {
                    const links = Array.from(
                        document.querySelectorAll('a[href*="/item.htm?id="]')
                    );
                    return links.slice(0, 20).map(a => ({
                        name: (a.innerText || a.textContent || '').trim(),
                        url: a.getAttribute('href') || '',
                        cityname: ''
                    }));
                }"""
            )
        except Exception as e:  # noqa: BLE001 - DOM extraction is best-effort
            logger.warning("DOM extraction failed: %s", e)
            return None

        if items:
            logger.info("Extracted %d result(s) from rendered DOM", len(items))
            return {"data": {"list": items}}
        return None

    def _try_parse_response(self, response) -> dict | None:
        """Best-effort JSON extraction from a Playwright response.

        Playwright's ``response.json()`` assumes UTF-8 text. Damai sometimes
        serves gzip-compressed or GBK-encoded responses that crash the default
        decoder and, if unhandled, propagate out of the response callback. This
        method tries the simple path first, then falls back to raw bytes with
        gzip/encoding handling, and finally returns ``None`` instead of raising.
        """
        # Fast path: works for plain UTF-8 JSON.
        try:
            return response.json()
        except Exception:
            pass

        # Slow path: get raw bytes and handle compression/encodings manually.
        try:
            body = response.body()
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not read response body: %s", e)
            return None

        # Decompress if it looks like gzip.
        if body.startswith(b"\x1f\x8b"):
            try:
                body = gzip.decompress(body)
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to decompress gzip response: %s", e)

        text = None
        for encoding in ("utf-8", "gbk", "gb18030", "latin-1"):
            try:
                text = body.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            logger.warning("Could not decode response body with any known encoding")
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning("Decoded body is not valid JSON: %s", e)
            return None

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

    def _now_iso(self) -> str:
        return datetime.now(TZ).isoformat()
