from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    is_admin: bool
    is_active: bool

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=1, max_length=255, description="Login username (an email address).")
    password: str = Field(min_length=8, max_length=255)
    is_admin: bool = False


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    is_active: bool | None = None
    is_admin: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=255)
