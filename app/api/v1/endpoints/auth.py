"""Authentication endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import UserRole
from app.infrastructure.database.session import get_db_session
from app.models.user import UserModel
from app.observability.logger import get_logger
from app.repositories.audit_repository import AuditRepository
from app.repositories.user_repository import UserRepository
from app.security.jwt_handler import create_access_token, create_refresh_token, decode_token
from app.security.password import hash_password, verify_password
from app.security.rbac import CurrentUser, RequireAdmin, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


# ── Request / Response schemas ────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    user_id: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: UserRole = UserRole.USER


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login_at: datetime | None = None

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    user_repo = UserRepository(session)
    audit_repo = AuditRepository(session)
    ip = request.client.host if request.client else None

    user = await user_repo.get_active_by_email(body.email)

    if not user or not verify_password(body.password, user.hashed_password):
        await audit_repo.log(
            action="auth:login",
            details={"email": body.email},
            ip_address=ip,
            status="failure",
            error_message="Invalid credentials",
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    await user_repo.update_last_login(user.id)

    access_token = create_access_token(
        subject=user.id,
        role=user.role,
        extra_claims={"email": user.email},
    )
    refresh_token = create_refresh_token(subject=user.id, role=user.role)

    await audit_repo.log(
        action="auth:login",
        user_id=user.id,
        details={"email": user.email},
        ip_address=ip,
        status="success",
    )
    await session.commit()

    logger.info("User logged in", email=user.email, role=user.role)
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=user.role,
        user_id=user.id,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    current_user: CurrentUser = Depends(RequireAdmin),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Admin-only endpoint to create new users."""
    user_repo = UserRepository(session)
    existing = await user_repo.get_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email '{body.email}' already exists",
        )

    user = UserModel(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=body.role.value,
        is_active=True,
    )
    user = await user_repo.create(user)
    await session.commit()

    logger.info("User registered", email=user.email, role=user.role, by=current_user.email)
    return UserResponse.model_validate(user)


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> LoginResponse:
    """Exchange a refresh token for a new access token."""
    from app.domain.exceptions.domain_exceptions import InvalidCredentialsError

    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type"
            )
        user_id = payload.get("sub")
        role = payload.get("role", "user")
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive"
        )

    access_token = create_access_token(
        subject=user.id,
        role=user.role,
        extra_claims={"email": user.email},
    )
    new_refresh = create_refresh_token(subject=user.id, role=user.role)
    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        role=user.role,
        user_id=user.id,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(current_user.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserResponse.model_validate(user)