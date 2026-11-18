from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BootstrapRequest(BaseModel):
    email: str = Field(min_length=3)
    full_name: str | None = None
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return auth_service.normalize_email(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return auth_service.normalize_email(value)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut


class AuthStatus(BaseModel):
    enabled: bool
    bootstrapped: bool


class MessageResponse(BaseModel):
    message: str


def user_response(user) -> UserOut:
    return UserOut(**auth_service.user_to_dict(user))


@router.post("/bootstrap", response_model=UserOut)
def bootstrap(payload: BootstrapRequest, db: Session = Depends(get_db)):
    if auth_service.is_bootstrapped(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bootstrap is only available when no users exist.",
        )
    try:
        user = auth_service.create_user(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            role="admin",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return user_response(user)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_service.create_access_token(db, user.id)
    return LoginResponse(
        access_token=token.token,
        expires_at=auth_service.as_utc(token.expires_at),
        user=user_response(user),
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
    user=Depends(auth_service.get_current_user),
):
    token_value = auth_service.bearer_token(authorization)
    if token_value is not None:
        auth_service.revoke_token(db, token_value)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=UserOut | None)
def read_me(user=Depends(auth_service.get_current_user)):
    return user_response(user) if user is not None else None


@router.get("/status", response_model=AuthStatus)
def auth_status(db: Session = Depends(get_db)):
    return AuthStatus(
        enabled=auth_service.settings.auth_enabled,
        bootstrapped=auth_service.is_bootstrapped(db),
    )
