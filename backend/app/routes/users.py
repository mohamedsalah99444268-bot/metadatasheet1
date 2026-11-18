from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..services import auth_service
from .auth import UserOut

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    dependencies=[Depends(auth_service.require_admin)],
)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=255)
    role: Literal["admin", "user"] | None = None
    is_active: bool | None = None


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return [UserOut(**auth_service.user_to_dict(user)) for user in users]


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return UserOut(**auth_service.user_to_dict(user))


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    user.is_active = False
    auth_service.revoke_user_tokens(db, user)
    db.refresh(user)
    return UserOut(**auth_service.user_to_dict(user))
