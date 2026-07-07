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


@pytest.fixture
def config_pushplus():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="pptoken456",
        wechat_provider="pushplus",
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


@responses.activate
def test_send_pushplus(config_pushplus):
    """PushPlus provider branch: posts to pushplus.plus/send with token/title/content."""
    responses.add(
        responses.POST,
        "https://www.pushplus.plus/send",
        json={"code": 200, "msg": "success"},
        status=200,
    )

    notifier = WeChatNotifier(config_pushplus)
    notifier.send(
        title="刘宪华演唱会-苏州站",
        url="https://detail.damai.cn/item.htm?id=123",
        status="on_sale",
    )

    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert call.request.url == "https://www.pushplus.plus/send"
    body = urllib.parse.unquote(call.request.body)
    # PushPlus payload includes the token and content fields.
    assert "pptoken456" in body
    assert "刘宪华演唱会-苏州站" in body
    assert "detail.damai.cn" in body


@responses.activate
def test_send_retries_on_transient_failure(config_serverchan, monkeypatch):
    """A transient 5xx is retried; the third attempt succeeds and the call returns."""
    # Patch sleep so the test doesn't actually wait. with_retry defaults to
    # time.sleep imported in the retry module.
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        status=500,
    )
    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        status=500,
    )
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

    assert len(responses.calls) == 3


@responses.activate
def test_send_raises_after_exhausting_retries(config_serverchan, monkeypatch):
    """All retries failing re-raises the last error so run_once can flag the failure."""
    import retry as retry_mod

    monkeypatch.setattr(retry_mod.time, "sleep", lambda _: None)

    for _ in range(3):
        responses.add(
            responses.POST,
            "https://sctapi.ftqq.com/sckey123.send",
            status=500,
        )

    notifier = WeChatNotifier(config_serverchan)
    with pytest.raises(Exception):
        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

    assert len(responses.calls) == 3
