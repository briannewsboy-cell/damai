import urllib.parse

import responses
import pytest
from config import Config
from notifiers.wechat import WeChatNotifier


@pytest.fixture
def config_serverchan():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="sckey123",
        wechat_provider="serverchan",
    )


@responses.activate
def test_send_serverchan(config_serverchan):
    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        json={"code": 0, "message": "success"},
        status=200,
    )

    notifier = WeChatNotifier(config_serverchan)
    notifier.send(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status="on_sale",
    )

    assert len(responses.calls) == 1
    body = urllib.parse.unquote(responses.calls[0].request.body)
    assert "刘宪华演唱会-苏州站" in body
    assert "detail.damai.cn" in body
