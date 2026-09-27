from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.jwt_handler import verify_token
from app.constants.roles import Roles
from app.crud.user import get_user_by_mobile
from app.database.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = verify_token(token)

    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    mobile = payload.get("sub")

    if not mobile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_mobile(db, mobile)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # کاربر غیرفعال (اخراج/تعلیق) نباید با توکن معتبرِ باقی‌مانده هم
    # بتواند ادامه دهد. پیش از این is_active در هیچ‌کجای وب بررسی
    # نمی‌شد و توکن تا ۶۰ دقیقه/۷ روز همچنان کار می‌کرد.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="این حساب کاربری غیرفعال شده است.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Access tokens carry the user's session generation. Bumping it on
    # password changes/resets/deactivation invalidates old access tokens
    # immediately instead of waiting for JWT expiry.
    token_session_version = payload.get("sv")\n    if token_session_version is None:\n        raise HTTPException(\n            status_code=status.HTTP_401_UNAUTHORIZED,\n            detail="Invalid or expired token.",\n            headers={"WWW-Authenticate": "Bearer"},\n        )
    if token_session_version != user.session_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def require_admin(
    current_user: User = Depends(get_current_user),
):
    if current_user.role != Roles.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    return current_user


def require_roles(*roles):
    def checker(
        current_user: User = Depends(get_current_user),
    ):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )

        return current_user

    return checker