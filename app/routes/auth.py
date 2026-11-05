from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user_schema import UserCreate, UserRead
from app.services import user_service

router = APIRouter(tags=["auth"])


@router.post(
    "/auth",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Username is already taken"}},
)
def create_user(
    user_create: UserCreate,
    session: Session = Depends(get_db),
):
    try:
        return user_service.create_user(session, user_create)
    except user_service.UsernameTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username is already taken")
