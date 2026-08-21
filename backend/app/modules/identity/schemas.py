from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=10, max_length=256)
    device_id: str = Field(min_length=2, max_length=160)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=512)
    device_id: str = Field(min_length=2, max_length=160)


class WarehouseCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=160)
    server_group: str = Field(default="primary", min_length=2, max_length=80)
    active: bool = True


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9_.@-]+$")
    name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=256)
    roles: list[str] = Field(min_length=1)
    warehouse_ids: list[str] = Field(default_factory=list)
    active: bool = True
    force_password_change: bool = True


class UserUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    roles: list[str] | None = None
    warehouse_ids: list[str] | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)
    force_password_change: bool | None = None


class AdminPasswordResetRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)
    device_id: str = Field(min_length=2, max_length=160)
