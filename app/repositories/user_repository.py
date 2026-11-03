from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.user import User
from app.database import engine

def create_user(username, password):
    user = User(username = username, password = password)
    with Session(engine) as session:
        session.add(user)
        session.commit()