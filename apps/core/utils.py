"""Shared helpers: reset tokens, email, Expo push notifications."""
from __future__ import annotations

import requests
from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import BadSignature, Signer, TimestampSigner

reset_signer = TimestampSigner(salt="password-reset")


def make_reset_token(user_id: int, kind: str) -> str:
    """kind: 'trainer' or 'client'. Token valid for 24h (matches JWT expiry)."""
    return reset_signer.sign(f"{kind}:{user_id}")


def read_reset_token(token: str) -> tuple[str, int] | None:
    """Return (kind, user_id) or None when invalid/expired."""
    try:
        value = reset_signer.unsign(token, max_age=60 * 60 * 24)
        kind, _, uid = value.partition(":")
        return kind, int(uid)
    except (BadSignature, ValueError):
        return None


def send_reset_email(email: str, name: str, reset_url: str) -> None:
    subject = "Reset your password"
    body = (
        f"Hi {name},\n\n"
        f"Use the link below to reset your password. The link expires in 24 hours.\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can ignore this email.\n"
    )
    send_mail(subject, body, None, [email], fail_silently=True)


def send_expo_push(tokens: list[str], title: str, body: str, data: dict | None = None) -> int:
    """Send an Expo push notification. Returns number of messages accepted."""
    if not tokens:
        return 0
    messages = [
        {"to": t, "title": title, "body": body, "sound": "default", "data": data or {}}
        for t in tokens
        if t.startswith("ExponentPushToken") or t.startswith("ExpoPushToken")
    ]
    if not messages:
        return 0
    try:
        resp = requests.post(
            "https://exp.host/--/api/v2/push/send",
            json=messages,
            timeout=10,
        )
        if resp.ok:
            data_out = resp.json().get("data", [])
            return sum(1 for d in data_out if d.get("status") in ("ok", "scheduled"))
    except requests.RequestException:
        pass
    return 0


def user_push_tokens(user) -> list[str]:
    from apps.fitness.models import PushToken

    return list(
        PushToken.objects.filter(user_type=user.push_user_type, user_id=user.id).values_list(
            "token", flat=True
        )
    )
