import responses
import pytest
from config import Config
from checkers.http import HttpDamaiChecker


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
