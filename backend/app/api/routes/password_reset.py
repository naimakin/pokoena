from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.schemas.password_reset import PasswordResetPreview, PasswordResetSubmit
from app.services import audit
from app.services.password_reset import PasswordResetError, apply_password_reset, get_reset_preview

router = APIRouter(prefix="/reset-password", tags=["password-reset"])


@router.get("/{token}", response_model=PasswordResetPreview)
def preview_password_reset(token: str, db: Session = Depends(get_db)) -> PasswordResetPreview:
    try:
        user = get_reset_preview(db, token)
    except PasswordResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PasswordResetPreview(email=user.email, is_platform_admin=user.is_platform_admin)


@router.post(
    "/{token}",
    response_model=PasswordResetPreview,
    dependencies=[Depends(rate_limit("password_reset_accept", limit=10, window_seconds=60))],
)
def submit_password_reset(
    token: str, payload: PasswordResetSubmit, db: Session = Depends(get_db)
) -> PasswordResetPreview:
    try:
        user = apply_password_reset(db, token, payload.password)
    except PasswordResetError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit.log(
        "password_reset.completed", tenant_id=None, actor_user_id=user.id,
        target_type="user", target_id=user.id,
    )
    return PasswordResetPreview(email=user.email, is_platform_admin=user.is_platform_admin)
