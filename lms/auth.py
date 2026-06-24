"""
Authentication System - JWT generation & validation untuk Simple LMS API.
"""
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from ninja.errors import HttpError
from ninja.security import HttpBearer

from lms.models import User


def _now():
    return datetime.now(timezone.utc)


def create_access_token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "username": user.username,
        "role": user.role,
        "token_type": "access",
        "iat": _now(),
        "exp": _now() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user: User) -> str:
    payload = {
        "user_id": user.id,
        "token_type": "refresh",
        "iat": _now(),
        "exp": _now() + timedelta(days=settings.JWT_REFRESH_TOKEN_LIFETIME_DAYS),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def generate_tokens(user: User) -> dict:
    """Generate sepasang token (access + refresh) untuk user yang login."""
    return {
        "access": create_access_token(user),
        "refresh": create_refresh_token(user),
        "token_type": "bearer",
    }


def decode_token(token: str) -> dict:
    """Decode & validasi JWT. Raise HttpError(401) jika invalid/expired."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HttpError(401, "Token sudah expired, silakan refresh atau login ulang")
    except jwt.InvalidTokenError:
        raise HttpError(401, "Token tidak valid")


class JWTAuth(HttpBearer):
    """
    Token validation middleware untuk Django Ninja.

    Dipasang di endpoint dengan `auth=jwt_auth`. Django Ninja otomatis:
    - Membaca header `Authorization: Bearer <token>`
    - Memanggil method `authenticate()` di bawah ini
    - Jika return value bukan None -> disimpan ke `request.auth`
    - Jika return None / raise HttpError -> response 401 Unauthorized
    """

    def authenticate(self, request, token: str):
        payload = decode_token(token)

        if payload.get("token_type") != "access":
            raise HttpError(401, "Token ini bukan access token yang valid")

        try:
            user = User.objects.get(pk=payload["user_id"])
        except User.DoesNotExist:
            raise HttpError(401, "User pemilik token tidak ditemukan")

        if not user.is_active:
            raise HttpError(401, "Akun tidak aktif")

        return user


# Instance siap pakai, di-import di api.py: auth=jwt_auth
jwt_auth = JWTAuth()