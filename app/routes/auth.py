from fastapi import APIRouter
from app.schemas.user_schema import UserCreate
from app.database import database

router = APIRouter()

# TODO: return 201 with a response schema that excludes the password (currently echoes the request body)
@router.post("/auth/")
def create_user(user_create: UserCreate):
    database.create_user(**user_create.model_dump())
    return user_create

