import urllib.parse

import responses
import pytest
from config import Config
from notifiers.wechat import WeChatNotifier


@pytest.fixture
def config_serverchan():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        concert_detail_url=None,
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
        concert_detail_url=None,
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


@responses.activate
def test_send_serverchan_raises_on_api_error_code(config_serverchan):
    """HTTP 200 with a nonzero ServerChan ``code`` is an API-level failure.

    raise_for_status() passes, but the JSON body indicates the request was
    rejected (e.g. bad token). The notifier must raise so run_once can flag
    the failure and retry on the next run. The call is not retried because
    RuntimeError is not in RETRY_EXCEPTIONS (permanent error, not transient).
    """
    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        json={"code": 40001, "message": "bad token"},
        status=200,
    )

    notifier = WeChatNotifier(config_serverchan)
    with pytest.raises(RuntimeError, match="serverchan API error"):
        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

    # Not retried — RuntimeError is not in RETRY_EXCEPTIONS.
    assert len(responses.calls) == 1


@responses.activate
def test_send_pushplus_raises_on_api_error_code(config_pushplus):
    """HTTP 200 with a non-200 PushPlus ``code`` is an API-level failure.

    PushPlus's success code is 200 (not 0). Any other code means the message
    was not delivered; raise so run_once can handle it.
    """
    responses.add(
        responses.POST,
        "https://www.pushplus.plus/send",
        json={"code": 500, "msg": "internal error"},
        status=200,
    )

    notifier = WeChatNotifier(config_pushplus)
    with pytest.raises(RuntimeError, match="pushplus API error"):
        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

    assert len(responses.calls) == 1


@responses.activate
def test_send_raises_on_non_json_response(config_serverchan):
    """A non-JSON 200 response is treated as an error (malformed API reply)."""
    responses.add(
        responses.POST,
        "https://sctapi.ftqq.com/sckey123.send",
        body="<html>gateway error</html>",
        status=200,
    )

    notifier = WeChatNotifier(config_serverchan)
    with pytest.raises(RuntimeError, match="non-JSON response"):
        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

    assert len(responses.calls) == 1
