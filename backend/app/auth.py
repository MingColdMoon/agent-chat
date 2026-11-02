from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.database import UserRecord
from app.models import UserInfo


password_hash = PasswordHash.recommended()


class AuthTokenError(ValueError):
    pass


@dataclass(frozen=True)
class AuthContext:
    user: UserInfo
    token: str
    payload: dict[str, Any]


async def hash_password(password: str) -> str:
    return await run_in_threadpool(password_hash.hash, password)


async def verify_password(password: str, hashed_password: str) -> bool:
    return await run_in_threadpool(
        password_hash.verify,
        password,
        hashed_password,
    )


def create_access_token(
    user: UserRecord,
    settings: Settings,
) -> tuple[str, datetime, str]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.jwt_expiration_minutes)
    jti = secrets.token_urlsafe(24)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "type": "access",
        "jti": jti,
        "iss": settings.jwt_issuer,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_at, jti


def decode_access_token(token: str, settings: Settings) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={
                "require": ["sub", "type", "jti", "iss", "iat", "exp"],
            },
        )
    except jwt.PyJWTError as error:
        raise AuthTokenError("JWT 无效或已过期") from error
    if payload.get("type") != "access":
        raise AuthTokenError("JWT 类型不正确")
    return payload


def user_to_info(user: UserRecord) -> UserInfo:
    created_at = user.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return UserInfo(
        id=str(user.id),
        username=user.username,
        created_at=created_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    )

