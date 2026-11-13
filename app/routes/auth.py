from fastapi import APIRouter, Depends, HTTPException, status

from app.config import ACCESS_TOKEN_MAX_AGE
from app.db.engine import get_db
from app.db.interface import Database
from app.schemas.user_schema import LoginRequest, Token, UserCreate, UserRead
from app.security import create_access_token
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
    db: Database = Depends(get_db),
):
    try:
        return user_service.create_user(db, user_create)
    except user_service.UsernameTakenError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Username is already taken") from None


@router.post(
    "/login",
    response_model=Token,
    responses={401: {"description": "Invalid username or password"}},
)
def login(
    credentials: LoginRequest,
    db: Database = Depends(get_db),
):
    """Exchange a username and password for an access token (JWT), valid for one hour."""
    user = user_service.authenticate(db, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return Token(access_token=create_access_token(user.id), expires_in=ACCESS_TOKEN_MAX_AGE)
