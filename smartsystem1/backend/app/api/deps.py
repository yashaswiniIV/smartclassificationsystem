from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status

from app.core.db import SessionDep
from app.core.security import decode_access_token
from app.models.enums import UserRole
from app.models.user import User

_UNAUTH = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "not_authenticated", "message": "Invalid or missing credentials"},
    headers={"WWW-Authenticate": "Bearer"},
)


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _UNAUTH
    return token


async def get_current_user(request: Request, db: SessionDep) -> User:
    token = _bearer(request)
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "token_expired", "message": "Access token expired"},
        ) from e
    except jwt.PyJWTError as e:
        raise _UNAUTH from e

    user = await db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise _UNAUTH
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(
    *roles: UserRole,
) -> Callable[[User], Coroutine[Any, Any, User]]:
    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "forbidden", "message": "Insufficient role"},
            )
        return user

    return _check


def client_meta(request: Request) -> tuple[str | None, str | None]:
    ua = request.headers.get("User-Agent")
    ip = request.client.host if request.client else None
    return ua, ip


# Reusable role-gated dependencies. "Staff" = official (incl. department heads) or admin.
StaffUser = Annotated[User, Depends(require_roles(UserRole.official, UserRole.admin))]
AdminUser = Annotated[User, Depends(require_roles(UserRole.admin))]
