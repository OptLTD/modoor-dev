"""Login-code delivery. Channel comes from ``MODOOR_NOTIFY``: mock, smtp, or aliyun-sms."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import smtplib
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import quote

import httpx

from modoor.core.errors import AppError
from modoor.core.settings import get_settings

log = logging.getLogger("modoor.notify")

_CHANNELS = frozenset({"mock", "smtp", "aliyun-sms"})
_ALIYUN_ENDPOINT = "https://dysmsapi.aliyuncs.com/"
_SMS_TTL_MINUTES = 5


def notify_channel() -> str:
    """Configured channel, or ``""`` when delivery is left unset."""
    name = (get_settings().modoor_notify or "").strip().lower()
    if not name:
        return ""
    if name not in _CHANNELS:
        raise AppError("validation_error", f"不支持的通知通道: {name}")
    return name


def send_code(*, channel: str, target: str, code: str) -> None:
    """Deliver a one-time code. ``target`` is an email or phone, except for mock."""
    name = (channel or "").strip().lower()
    if name == "mock":
        log.info("captcha mock target=%s code=%s", target or "-", code)
        return
    if name == "smtp":
        _send_smtp(target, code)
        return
    if name == "aliyun-sms":
        _send_aliyun(target, code)
        return
    raise AppError("validation_error", f"不支持的通知通道: {name}")


def _send_smtp(target: str, code: str) -> None:
    settings = get_settings()
    host = (settings.modoor_smtp_host or "").strip()
    sender = (settings.modoor_smtp_from or settings.modoor_smtp_user or "").strip()
    if not host or not sender:
        raise AppError("validation_error", "未配置邮件，无法发送验证码")
    if not (target or "").strip():
        raise AppError("validation_error", "该账号未绑定邮箱")
    message = EmailMessage()
    message["Subject"] = "登录验证码"
    message["From"] = sender
    message["To"] = target.strip()
    message.set_content(f"您的验证码是 {code}，{_SMS_TTL_MINUTES} 分钟内有效。")
    port = int(settings.modoor_smtp_port or 587)
    user = (settings.modoor_smtp_user or "").strip()
    password = settings.modoor_smtp_pass or ""
    try:
        if port == 465:
            smtp: smtplib.SMTP = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            smtp = smtplib.SMTP(host, port, timeout=15)
        try:
            if port != 465 and settings.modoor_smtp_tls:
                smtp.starttls()
            if user:
                smtp.login(user, password)
            smtp.send_message(message)
        finally:
            smtp.quit()
    except Exception as exc:
        log.warning("smtp captcha failed: %s", exc)
        raise AppError("validation_error", "验证码发送失败") from exc


def _send_aliyun(phone: str, code: str) -> None:
    settings = get_settings()
    ak_id = (settings.modoor_aliyun_sms_ak_id or "").strip()
    ak_secret = settings.modoor_aliyun_sms_ak_secret or ""
    sign = (settings.modoor_aliyun_sms_sign or "").strip()
    template = (settings.modoor_aliyun_sms_template or "").strip()
    if not ak_id or not ak_secret or not sign or not template:
        raise AppError("validation_error", "未配置阿里云短信，无法发送验证码")
    if not (phone or "").strip():
        raise AppError("validation_error", "该账号未绑定手机号")
    params = _aliyun_sms_params(
        ak_id=ak_id,
        ak_secret=ak_secret,
        phone=phone.strip(),
        sign=sign,
        template=template,
        code=code,
    )
    try:
        response = httpx.post(_ALIYUN_ENDPOINT, data=params, timeout=15)
        if response.status_code >= 400:
            log.warning("aliyun captcha http %s", response.status_code)
            raise AppError("validation_error", "验证码发送失败")
        body = response.json()
    except AppError:
        raise
    except Exception as exc:
        log.warning("aliyun captcha failed: %s", exc)
        raise AppError("validation_error", "验证码发送失败") from exc
    if str(body.get("Code") or "") != "OK":
        log.warning(
            "aliyun captcha rejected code=%s message=%s",
            body.get("Code"),
            body.get("Message"),
        )
        raise AppError("validation_error", "验证码发送失败")


def _aliyun_sms_params(
    *,
    ak_id: str,
    ak_secret: str,
    phone: str,
    sign: str,
    template: str,
    code: str,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> dict[str, str]:
    params = {
        "AccessKeyId": ak_id,
        "Action": "SendSms",
        "Format": "JSON",
        "PhoneNumbers": phone,
        "RegionId": "cn-hangzhou",
        "SignName": sign,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureNonce": nonce or uuid.uuid4().hex,
        "SignatureVersion": "1.0",
        "TemplateCode": template,
        "TemplateParam": json.dumps({"code": code}, separators=(",", ":")),
        "Timestamp": timestamp or _utc_timestamp(),
        "Version": "2017-05-25",
    }
    params["Signature"] = _pop_sign("POST", params, ak_secret)
    return params


def _pop_sign(method: str, params: dict[str, str], ak_secret: str) -> str:
    """Alibaba Cloud RPC (POP) signature."""
    canonical = "&".join(
        f"{_percent(key)}={_percent(params[key])}" for key in sorted(params)
    )
    string_to_sign = f"{method.upper()}&{_percent('/')}&{_percent(canonical)}"
    digest = hmac.new(
        f"{ak_secret}&".encode(),
        string_to_sign.encode(),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode()


def _percent(value: str) -> str:
    return quote(str(value), safe="-_.~")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
