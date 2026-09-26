from pydantic import BaseModel


class LoginRequest(BaseModel):
    mobile: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    """بدنه‌ی درخواست خروج — توکن تمدیدی که باید سمت سرور باطل شود."""

    refresh_token: str
