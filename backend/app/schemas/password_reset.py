from pydantic import BaseModel


class PasswordResetLinkOut(BaseModel):
    email: str
    reset_url: str


class PasswordResetPreview(BaseModel):
    email: str
    is_platform_admin: bool


class PasswordResetSubmit(BaseModel):
    password: str
