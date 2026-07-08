from unittest.mock import Mock, patch
import pytest
from config import Config
from notifiers.email import EmailNotifier


@pytest.fixture
def config():
    return Config(
        concert_keyword="刘宪华 苏州 演唱会",
        concert_detail_url=None,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )


def test_send_email(config):
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

        instance.starttls.assert_called_once()
        instance.login.assert_called_once_with("sender@example.com", "secret")
        call_args = instance.send_message.call_args
        msg = call_args[0][0]
        assert msg["To"] == "receiver@example.com"
        assert msg["From"] == "sender@example.com"
        assert call_args.kwargs.get("to_addrs") == ["receiver@example.com"]
        assert "刘宪华演唱会-苏州站" in msg.get_payload()[0].get_payload(decode=True).decode()


def test_send_email_subject_for_on_sale(config):
    """on_sale status renders '已开售' in the subject (not the raw status)."""
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

        msg = instance.send_message.call_args[0][0]
        assert msg["Subject"] == "[开票提醒] 刘宪华演唱会-苏州站 已开售"


def test_send_email_subject_for_checker_failed(config):
    """checker_failed status must not say '已开售' in the subject.

    Regression: the subject was hardcoded to '已开售' for all statuses,
    which was misleading for checker-failure alerts. It now renders a
    sensible label ('检查器异常') instead of the raw status string.
    """
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="检查器失效，请人工查看",
            url="",
            status="checker_failed",
        )

        msg = instance.send_message.call_args[0][0]
        assert "已开售" not in msg["Subject"]
        assert "检查器异常" in msg["Subject"]
        assert "checker_failed" not in msg["Subject"]
        # Body also uses the label, not the raw status.
        body = msg.get_payload()[0].get_payload(decode=True).decode()
        assert "检查器异常" in body
        assert "checker_failed" not in body


def test_send_email_subject_for_unknown_status(config):
    """A truly unknown status falls back to a generic label, not the raw string."""
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="something_unexpected",
        )

        msg = instance.send_message.call_args[0][0]
        assert "something_unexpected" not in msg["Subject"]
        assert "未知状态" in msg["Subject"]


def test_send_email_to_multiple_recipients():
    """EMAIL_TO with comma-separated addresses sends to each recipient."""
    config = Config(
        concert_keyword="刘宪华 苏州 演唱会",
        concert_detail_url=None,
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="sender@example.com",
        smtp_password="secret",
        email_to="receiver1@example.com, receiver2@example.com",
        wechat_token="wx_token",
        wechat_provider="serverchan",
    )
    notifier = EmailNotifier(config)
    with patch("notifiers.email.smtplib.SMTP") as mock_smtp:
        instance = Mock()
        mock_smtp.return_value.__enter__ = Mock(return_value=instance)
        mock_smtp.return_value.__exit__ = Mock(return_value=False)

        notifier.send(
            title="刘宪华演唱会-苏州站",
            url="https://detail.damai.cn/item.htm?id=123",
            status="on_sale",
        )

        msg = instance.send_message.call_args[0][0]
        to_addrs = instance.send_message.call_args.kwargs.get("to_addrs")
        assert msg["To"] == "receiver1@example.com, receiver2@example.com"
        assert to_addrs == ["receiver1@example.com", "receiver2@example.com"]
