from sqlalchemy.orm import Session

from app.models.user import User

def create_user(session: Session, username: str, password: str):
    user = User(username = username, password = password)
    session.add(user)
    session.commit()