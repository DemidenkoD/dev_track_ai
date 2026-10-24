"""POST /api/v1/auth/login + GET /api/v1/auth/me.

Single predefined account validated against ADMIN_USERNAME/ADMIN_PASSWORD.
No registration endpoint exists (backend/AGENTS.md §2.1).
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core import security as jwt_security
from app.core.deps import get_current_user
from app.schemas.api_contracts import LoginRequest, TokenResponse, UserProfileSchema

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest) -> TokenResponse:
    if not jwt_security.verify_credentials(body.username, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token, expires_in = jwt_security.create_access_token(body.username)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserProfileSchema(username=body.username, role="reviewer"),
    )


@router.get("/me", response_model=UserProfileSchema)
def me(current_user: UserProfileSchema = Depends(get_current_user)) -> UserProfileSchema:
    return current_user
