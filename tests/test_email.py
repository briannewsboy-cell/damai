from unittest.mock import Mock, patch
import pytest
from config import Config
from notifiers.email import EmailNotifier


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
        call_args = instance.send_message.call_args[0][0]
        assert call_args["To"] == "receiver@example.com"
        assert call_args["From"] == "sender@example.com"
        assert "刘宪华演唱会-苏州站" in call_args.get_payload()[0].get_payload(decode=True).decode()
