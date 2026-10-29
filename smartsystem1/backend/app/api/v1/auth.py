from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.deps import CurrentUser, client_meta
from app.core.config import get_settings
from app.core.db import SessionDep
from app.core.ratelimit import auth_rate_limit, otp_rate_limit
from app.core.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.auth import (
    LoginIn,
    RegisterIn,
    TokenOut,
    UpdateMeIn,
    UserOut,
    VerifyEmailIn,
)
from app.services import otp as otp_service
from app.services import sessions as session_service
from app.services.email import send_otp

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

REFRESH_COOKIE = "refresh_token"
REFRESH_PATH = "/api/v1/auth"

# Generic to prevent account enumeration (security checklist).
_BAD_CREDS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail={"code": "invalid_credentials", "message": "Invalid email or password"},
)


def _set_refresh_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw,
        httponly=True,
        secure=settings.env != "dev",
        samesite="lax",
        path=REFRESH_PATH,
        max_age=settings.refresh_token_ttl_days * 86400,
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterIn, db: SessionDep, _: None = Depends(auth_rate_limit)
) -> dict[str, str]:
    existing = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()

    if existing is not None and existing.email_verified_at is not None:
        # Already a usable account. Stay enumeration-safe (identical response) and
        # issue no code — the right action for the caller is to log in.
        return {"status": "verification_sent"}

    if existing is not None:
        # Registered but never verified → unclaimed account. Let the latest signup
        # attempt win (update name/password) and re-issue a fresh code. This also
        # makes "Resend code" work by simply calling register again.
        existing.password_hash = hash_password(body.password)
        existing.full_name = body.full_name
        existing.preferred_language = body.preferred_language
    else:
        db.add(
            User(
                email=body.email,
                password_hash=hash_password(body.password),
                full_name=body.full_name,
                preferred_language=body.preferred_language,
                role=UserRole.citizen,
            )
        )
    await db.commit()

    otp = await otp_service.issue_otp(body.email)
    await send_otp(body.email, otp)
    resp = {"status": "verification_sent"}
    # Dev-only convenience: surface the code so the signup UI can show it without
    # digging through server logs. NEVER returned outside dev.
    if settings.env == "dev":
        resp["dev_otp"] = otp
    return resp


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailIn, db: SessionDep, _: None = Depends(otp_rate_limit)
) -> dict[str, str]:
    if not await otp_service.verify_otp(body.email, body.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_otp", "message": "Invalid or expired code"},
        )
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_otp", "message": "Invalid or expired code"},
        )
    if user.email_verified_at is None:
        user.email_verified_at = datetime.now(UTC)
        await db.commit()
    return {"status": "verified"}


@router.post("/login", response_model=TokenOut)
async def login(
    body: LoginIn,
    response: Response,
    request: Request,
    db: SessionDep,
    _: None = Depends(auth_rate_limit),
) -> TokenOut:
    user = (await db.execute(select(User).where(User.email == body.email))).scalar_one_or_none()
    if user is None:
        dummy_verify()  # equalize timing so missing emails aren't faster to reject
        raise _BAD_CREDS
    if not verify_password(body.password, user.password_hash):
        raise _BAD_CREDS
    if not user.is_active:
        raise _BAD_CREDS
    if user.email_verified_at is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_unverified", "message": "Verify your email first"},
        )

    ua, ip = client_meta(request)
    raw = await session_service.issue_session(db, user.id, user_agent=ua, ip=ip)
    await db.commit()

    _set_refresh_cookie(response, raw)
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=TokenOut)
async def refresh(response: Response, request: Request, db: SessionDep) -> TokenOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "no_refresh_token", "message": "Missing refresh token"},
        )
    ua, ip = client_meta(request)
    try:
        user, new_raw = await session_service.rotate_session(db, raw, user_agent=ua, ip=ip)
    except session_service.RefreshError as e:
        await db.commit()  # persist any family revocation
        response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "session_revoked", "message": "Please log in again"},
        ) from e

    await db.commit()
    _set_refresh_cookie(response, new_raw)
    return TokenOut(
        access_token=create_access_token(user.id, user.role.value),
        user=UserOut.model_validate(user),
    )


@router.post("/logout")
async def logout(response: Response, request: Request, db: SessionDep) -> dict[str, str]:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        await session_service.revoke_session(db, raw)
        await db.commit()
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
async def get_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UpdateMeIn, user: CurrentUser, db: SessionDep) -> User:
    if body.full_name is not None:
        user.full_name = body.full_name
    if body.phone is not None:
        user.phone = body.phone
    if body.preferred_language is not None:
        user.preferred_language = body.preferred_language
    await db.commit()
    await db.refresh(user)
    return user
