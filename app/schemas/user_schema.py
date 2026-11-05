from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=250)
    password: str = Field(min_length=8, max_length=128)
    repeat_password: str

    @model_validator(mode="after")
    def passwords_match(self) -> "UserCreate":
        if self.password != self.repeat_password:
            raise ValueError("passwords do not match")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
