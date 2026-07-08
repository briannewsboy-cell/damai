import responses
import pytest
from config import Config
from checkers.base import DamaiBlockedError
from checkers.http import HttpDamaiChecker
from checkers.playwright import PlaywrightDamaiChecker


@pytest.fixture
def config():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )


@responses.activate
def test_http_checker_finds_on_sale(config):
    with open("tests/fixtures/detail_on_sale.html", "r", encoding="utf-8") as f:
        detail_html = f.read()

    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={
            "data": {
                "list": [
                    {
                        "url": "/item.htm?id=123",
                        "name": "刘宪华演唱会-苏州站",
                        "cityname": "苏州",
                    }
                ]
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://detail.damai.cn/item.htm?id=123",
        body=detail_html,
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.on_sale is True
    assert result.title == "刘宪华演唱会-苏州站"
    assert "detail.damai.cn" in result.url


@responses.activate
def test_http_checker_finds_not_on_sale(config):
    with open("tests/fixtures/detail_not_sale.html", "r", encoding="utf-8") as f:
        detail_html = f.read()

    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={
            "data": {
                "list": [
                    {
                        "url": "/item.htm?id=456",
                        "name": "刘宪华演唱会-苏州站",
                        "cityname": "苏州",
                    }
                ]
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://detail.damai.cn/item.htm?id=456",
        body=detail_html,
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.on_sale is False
    assert result.status == "not_on_sale"


@responses.activate
def test_http_checker_uses_best_match(config):
    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={
            "data": {
                "list": [
                    {
                        "url": "/item.htm?id=111",
                        "name": "刘宪华音乐会-北京站",
                        "cityname": "北京",
                    },
                    {
                        "url": "/item.htm?id=222",
                        "name": "刘宪华演唱会-苏州站",
                        "cityname": "苏州",
                    },
                ]
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://detail.damai.cn/item.htm?id=222",
        body='<html><body><button class="buy__button">立即购买</button></body></html>',
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.title == "刘宪华演唱会-苏州站"
    assert "222" in result.url


@responses.activate
def test_http_checker_empty_results_returns_not_on_sale(config):
    """Empty search results must not raise; return a not_on_sale result instead.

    Previously this raised RuntimeError, failing the GitHub Actions job.
    """
    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={"data": {"list": []}},
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.on_sale is False
    assert result.status == "not_on_sale"
    assert result.title == ""
    assert result.url == ""
    assert result.checked_at is not None
    # No detail request should have been made.
    assert all("detail.damai.cn" not in call.request.url for call in responses.calls)


@responses.activate
def test_http_checker_retries_search_on_5xx(config, monkeypatch):
    """A transient 5xx on the search endpoint is retried up to 3 times."""
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    with open("tests/fixtures/detail_on_sale.html", "r", encoding="utf-8") as f:
        detail_html = f.read()

    # First two search calls fail, third succeeds.
    responses.add(
        responses.GET, "https://search.damai.cn/searchajax.html", status=500
    )
    responses.add(
        responses.GET, "https://search.damai.cn/searchajax.html", status=503
    )
    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={
            "data": {
                "list": [
                    {
                        "url": "/item.htm?id=123",
                        "name": "刘宪华演唱会-苏州站",
                        "cityname": "苏州",
                    }
                ]
            }
        },
        status=200,
    )
    responses.add(
        responses.GET,
        "https://detail.damai.cn/item.htm?id=123",
        body=detail_html,
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.on_sale is True
    # Exactly 3 search calls + 1 detail call.
    search_calls = [
        c for c in responses.calls if "search.damai.cn" in c.request.url
    ]
    assert len(search_calls) == 3


@responses.activate
def test_http_checker_raises_after_retries_exhausted(config, monkeypatch):
    """If all 3 search attempts fail, the last error propagates so run_once can alert."""
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    for _ in range(3):
        responses.add(
            responses.GET, "https://search.damai.cn/searchajax.html", status=500
        )

    checker = HttpDamaiChecker(config)
    with pytest.raises(Exception):
        checker.check()

    search_calls = [
        c for c in responses.calls if "search.damai.cn" in c.request.url
    ]
    assert len(search_calls) == 3


@responses.activate
def test_http_checker_detects_blocking_and_raises_damai_blocked(config, monkeypatch):
    """A CAPTCHA/anti-bot HTML page raises DamaiBlockedError instead of JSONDecodeError."""
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    # All retries return the same anti-bot page.
    anti_bot_html = "<html><script>window.location='_____tmd_____/punish?x5secdata=abc'</script></html>"
    for _ in range(3):
        responses.add(
            responses.GET,
            "https://search.damai.cn/searchajax.html",
            body=anti_bot_html,
            status=200,
        )

    checker = HttpDamaiChecker(config)
    with pytest.raises(DamaiBlockedError):
        checker.check()


@responses.activate
def test_http_checker_retries_on_transient_non_json(config, monkeypatch):
    """A transient non-JSON 200 is retried when no anti-bot marker is present."""
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        body="not json",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        body="still not json",
        status=200,
    )
    responses.add(
        responses.GET,
        "https://search.damai.cn/searchajax.html",
        json={"data": {"list": []}},
        status=200,
    )

    checker = HttpDamaiChecker(config)
    result = checker.check()

    assert result.status == "not_on_sale"
    search_calls = [
        c for c in responses.calls if "search.damai.cn" in c.request.url
    ]
    assert len(search_calls) == 3


