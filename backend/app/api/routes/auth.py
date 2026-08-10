from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.deps import COOKIE_NAME, ROLE_COOKIE_NAME, get_current_user
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.user import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> User:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(subject=str(user.id), role=user.role.value)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.env != "development",
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_expires_minutes * 60,
        path="/",
    )
    # Non-httpOnly companion cookie so the Next.js edge middleware can route by role
    # without verifying a JWT at the edge. It carries no authority: every API route
    # re-derives the role server-side from the signed session cookie above.
    response.set_cookie(
        key=ROLE_COOKIE_NAME,
        value=user.role.value,
        httponly=False,
        secure=settings.env != "development",
        samesite="lax",
        domain=settings.cookie_domain,
        max_age=settings.jwt_expires_minutes * 60,
        path="/",
    )
    return user


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, domain=settings.cookie_domain, path="/")
    response.delete_cookie(ROLE_COOKIE_NAME, domain=settings.cookie_domain, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
