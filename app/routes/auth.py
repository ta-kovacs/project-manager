from fastapi import APIRouter
from app.schemas.user_schema import UserCreate
from app.services import user_service

router = APIRouter()

# TODO: return 201 with a response schema that excludes the password (currently echoes the request body)
@router.post("/auth/")
def create_user(user_create: UserCreate):
    user_service.create_user(user_create)
    return user_create

