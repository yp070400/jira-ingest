"""JWT token creation and validation."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.config import get_settings
from app.domain.exceptions.domain_exceptions import InvalidCredentialsError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    subject: str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "access",
        "iat": _utcnow(),
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_refresh_token(subject: str, role: str) -> str:
    settings = get_settings()
    expire = _utcnow() + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": "refresh",
        "iat": _utcnow(),
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": True},
        )
        return payload
    except JWTError as e:
        raise InvalidCredentialsError() from e


def get_subject_from_token(token: str) -> str:
    payload = decode_token(token)
    sub = payload.get("sub")
    if not sub:
        raise InvalidCredentialsError()
    return sub


def get_role_from_token(token: str) -> str:
    payload = decode_token(token)
    role = payload.get("role")
    if not role:
        raise InvalidCredentialsError()
    return role