from __future__ import annotations

import json

import httpx
import pytest

from modoor.core.errors import AppError
from modoor.core.notify import _aliyun_sms_params, _pop_sign, notify_channel, send_code
from modoor.web.login_auth import _sms_phone
from modoor.core.settings import get_settings


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setenv("MODOOR_NOTIFY", "")
    monkeypatch.setenv("MODOOR_SMTP_HOST", "")
    monkeypatch.setenv("MODOOR_SMTP_PORT", "587")
    monkeypatch.setenv("MODOOR_SMTP_USER", "")
    monkeypatch.setenv("MODOOR_SMTP_PASS", "")
    monkeypatch.setenv("MODOOR_SMTP_FROM", "")
    monkeypatch.setenv("MODOOR_SMTP_TLS", "1")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_ID", "")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_SECRET", "")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_SIGN", "")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_TEMPLATE", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_sms_phone_normalizes_domestic_numbers():
    assert _sms_phone("+86 138-0013-8000") == "13800138000"
    assert _sms_phone("8613800138000") == "13800138000"
    assert _sms_phone("admin") == ""


def test_notify_channel_names(monkeypatch):
    assert notify_channel() == ""
    monkeypatch.setenv("MODOOR_NOTIFY", "SMTP")
    get_settings.cache_clear()
    assert notify_channel() == "smtp"
    monkeypatch.setenv("MODOOR_NOTIFY", "ding")
    get_settings.cache_clear()
    with pytest.raises(AppError, match="不支持的通知通道"):
        notify_channel()


def test_pop_signature_matches_aliyun_sample():
    params = {
        "AccessKeyId": "testid",
        "Action": "DescribeRegions",
        "Format": "XML",
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": "3ee8c1b8-83d3-44af-a94f-4e0ad82fd6cf",
        "SignatureVersion": "1.0",
        "Timestamp": "2016-02-23T12:46:24Z",
        "Version": "2014-05-26",
    }
    assert _pop_sign("GET", params, "testsecret") == "OLeaidS1JvxuMvnyHOwuJ+uX5qY="


def test_mock_channel_logs_code(caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="modoor.notify"):
        send_code(channel="mock", target="admin", code="123456")
    assert "code=123456" in caplog.text


def test_smtp_sends_plain_message(monkeypatch):
    sent: dict = {}

    class _SMTP:
        def __init__(self, host, port, timeout=None):
            sent["host"] = host
            sent["port"] = port
            sent["timeout"] = timeout

        def starttls(self):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = (user, password)

        def send_message(self, message):
            sent["subject"] = message["Subject"]
            sent["from"] = message["From"]
            sent["to"] = message["To"]
            sent["body"] = message.get_content()

        def quit(self):
            sent["quit"] = True

    monkeypatch.setenv("MODOOR_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MODOOR_SMTP_PORT", "587")
    monkeypatch.setenv("MODOOR_SMTP_USER", "bot")
    monkeypatch.setenv("MODOOR_SMTP_PASS", "secret")
    monkeypatch.setenv("MODOOR_SMTP_FROM", "noreply@example.com")
    get_settings.cache_clear()
    monkeypatch.setattr("modoor.core.notify.smtplib.SMTP", _SMTP)
    send_code(channel="smtp", target="user@example.com", code="654321")
    assert sent["host"] == "smtp.example.com"
    assert sent["port"] == 587
    assert sent["tls"] is True
    assert sent["login"] == ("bot", "secret")
    assert sent["from"] == "noreply@example.com"
    assert sent["to"] == "user@example.com"
    assert "654321" in sent["body"]
    assert sent["quit"] is True


def test_smtp_uses_ssl_on_465(monkeypatch):
    opened: dict = {}

    class _SSL:
        def __init__(self, host, port, timeout=None):
            opened["ssl"] = (host, port)

        def login(self, user, password):
            return None

        def send_message(self, message):
            opened["to"] = message["To"]

        def quit(self):
            return None

    monkeypatch.setenv("MODOOR_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MODOOR_SMTP_PORT", "465")
    monkeypatch.setenv("MODOOR_SMTP_FROM", "noreply@example.com")
    get_settings.cache_clear()
    monkeypatch.setattr("modoor.core.notify.smtplib.SMTP_SSL", _SSL)
    send_code(channel="smtp", target="user@example.com", code="111111")
    assert opened["ssl"] == ("smtp.example.com", 465)


def test_smtp_missing_host():
    with pytest.raises(AppError, match="未配置邮件"):
        send_code(channel="smtp", target="user@example.com", code="111111")


def test_aliyun_posts_signed_sms(monkeypatch):
    captured: dict = {}

    def _post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = dict(data)
        captured["timeout"] = timeout
        return httpx.Response(200, json={"Code": "OK", "Message": "OK"})

    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_ID", "akid")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_SECRET", "aksecret")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_SIGN", "模多")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_TEMPLATE", "SMS_100")
    get_settings.cache_clear()
    monkeypatch.setattr("modoor.core.notify.httpx.post", _post)
    send_code(channel="aliyun-sms", target="13800138000", code="246810")
    data = captured["data"]
    assert captured["url"] == "https://dysmsapi.aliyuncs.com/"
    assert data["PhoneNumbers"] == "13800138000"
    assert data["SignName"] == "模多"
    assert data["TemplateCode"] == "SMS_100"
    assert json.loads(data["TemplateParam"]) == {"code": "246810"}
    signed = {key: value for key, value in data.items() if key != "Signature"}
    assert data["Signature"] == _pop_sign("POST", signed, "aksecret")


def test_aliyun_rejects_provider_error(monkeypatch):
    def _post(url, data=None, timeout=None):
        return httpx.Response(200, json={"Code": "isv.BUSINESS_LIMIT_CONTROL", "Message": "限流"})

    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_ID", "akid")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_AK_SECRET", "aksecret")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_SIGN", "模多")
    monkeypatch.setenv("MODOOR_ALIYUN_SMS_TEMPLATE", "SMS_100")
    get_settings.cache_clear()
    monkeypatch.setattr("modoor.core.notify.httpx.post", _post)
    with pytest.raises(AppError, match="验证码发送失败"):
        send_code(channel="aliyun-sms", target="13800138000", code="246810")


def test_aliyun_params_shape():
    params = _aliyun_sms_params(
        ak_id="akid",
        ak_secret="aksecret",
        phone="13800138000",
        sign="模多",
        template="SMS_100",
        code="246810",
        nonce="nonce",
        timestamp="2026-10-16T00:00:00Z",
    )
    assert params["Action"] == "SendSms"
    assert params["Version"] == "2017-05-25"
    assert "Signature" in params
