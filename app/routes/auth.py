from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas.user_schema import UserCreate
from app.services import user_service
from app.database import get_db

router = APIRouter()

# TODO: return 201 with a response schema that excludes the password (currently echoes the request body)
@router.post("/auth/")
def create_user(
    user_create: UserCreate,
    session: Session = Depends(get_db)
):
    user_service.create_user(session, user_create = user_create)
    return user_create

