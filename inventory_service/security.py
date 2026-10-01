import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt import InvalidTokenError

from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="http://localhost:8000/api/v1/auth/token")


@dataclass(frozen=True)
class Principal:
    user_id: uuid.UUID
    role: str


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_principal(token: str = Depends(oauth2_scheme)) -> Principal:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "role", "iat", "exp"]},
        )
        user_id = uuid.UUID(payload["sub"])
        role = payload["role"]
        if role not in {"customer", "admin"}:
            raise ValueError("Unknown role")
    except (InvalidTokenError, ValueError, TypeError, KeyError) as exc:
        raise authentication_error() from exc
    return Principal(user_id=user_id, role=role)


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
    return principal
