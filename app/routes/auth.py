from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user_schema import LoginRequest, UserCreate, UserRead
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


# TODO: issue an access token (JWT) here once authorization is implemented
@router.post(
    "/login",
    response_model=UserRead,
    responses={401: {"description": "Invalid username or password"}},
)
def login(
    credentials: LoginRequest,
    session: Session = Depends(get_db),
):
    user = user_service.authenticate(session, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return user
