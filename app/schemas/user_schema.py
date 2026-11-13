from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

PASSWORD_RULES = (
    f"at least {PASSWORD_MIN_LENGTH} characters, with a lowercase letter, an uppercase letter and a digit, "
    "and not containing the username"
)


def password_problems(password: str, username: str) -> list[str]:
    """What's wrong with a new password (empty when it is strong enough).

    Only checked when registering: existing passwords keep working at login.
    """
    missing = []
    if not any(c.islower() for c in password):
        missing.append("a lowercase letter")
    if not any(c.isupper() for c in password):
        missing.append("an uppercase letter")
    if not any(c.isdigit() for c in password):
        missing.append("a digit")

    problems = []
    if missing:
        problems.append(f"password must contain {', '.join(missing)}")
    if username and username.casefold() in password.casefold():
        problems.append("password must not contain the username")
    return problems


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=250)
    password: str = Field(
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description=f"Must be {PASSWORD_RULES}",
    )
    repeat_password: str

    @model_validator(mode="after")
    def password_is_strong_and_repeated(self) -> "UserCreate":
        problems = password_problems(self.password, self.username)
        if self.password != self.repeat_password:
            problems.append("passwords do not match")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class LoginRequest(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    """An access token for the `Authorization: Bearer <access_token>` header of protected requests."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(description="Seconds until the access token expires")
