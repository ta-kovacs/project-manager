from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import DATABASE_URL
from app.models.user import User

engine = create_engine(
    DATABASE_URL,
    echo=True
)
    
def create_user(username, password, repeat_password):
    ## TODO proper check for valid user creation (there is a password provided, no overlapping user)
    if password == repeat_password:
        with Session(engine) as session:
            user = User(username = username, password = password)
            session.add(user)
            session.commit()

def get_all_users():
    with Session(engine) as session:
        users = session.scalars(select(User)).all()
        for user in users:
            print(user.username, user.password)

        return users