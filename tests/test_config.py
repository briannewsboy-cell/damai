import os
import pytest
from config import load_config


def test_load_config_with_required_values(monkeypatch):
    monkeypatch.setenv("CONCERT_KEYWORD", "刘宪华 苏州 演唱会")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "receiver@example.com")
    monkeypatch.setenv("WECHAT_TOKEN", "wx_token")
    monkeypatch.setenv("WECHAT_PROVIDER", "serverchan")

    config = load_config()
    assert config.concert_keyword == "刘宪华 苏州 演唱会"
    assert config.concert_detail_url is None
    assert config.smtp_host == "smtp.example.com"
    assert config.smtp_port == 587
    assert config.email_to == "receiver@example.com"
    assert config.wechat_provider == "serverchan"


def test_load_config_with_detail_url(monkeypatch):
    monkeypatch.setenv("CONCERT_KEYWORD", "刘宪华 苏州 演唱会")
    monkeypatch.setenv("CONCERT_DETAIL_URL", "https://detail.damai.cn/item.htm?id=1061600015576")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("EMAIL_TO", "receiver@example.com")
    monkeypatch.setenv("WECHAT_TOKEN", "wx_token")
    monkeypatch.setenv("WECHAT_PROVIDER", "serverchan")

    config = load_config()
    assert config.concert_detail_url == "https://detail.damai.cn/item.htm?id=1061600015576"
