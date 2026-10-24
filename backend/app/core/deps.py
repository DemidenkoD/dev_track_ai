"""FastAPI dependencies: DB session + single-account JWT authentication."""

from collections.abc import Iterator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core import security as jwt_security
from app.db.session import SessionLocal
from app.schemas.api_contracts import UserProfileSchema

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Iterator[Session]:
    """Yield a SQLAlchemy session (override in tests with SQLite fixtures)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> UserProfileSchema:
    """Validate the bearer JWT for the single predefined account."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt_security.decode_access_token(token)
    except jwt.PyJWTError:
        raise credentials_exception
    username = payload.get("sub")
    role = payload.get("role", "reviewer")
    if not username:
        raise credentials_exception
    return UserProfileSchema(username=username, role=role)
