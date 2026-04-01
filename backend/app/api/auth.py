from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.database import get_db
from app.schemas.schemas import AppRole, AuthUser

bearer_scheme = HTTPBearer()

JWT_ALGORITHM = "HS256"


TOKEN_EXPIRY_HOURS = 4


def create_jwt(
    developer_id: int,
    github_username: str,
    app_role: str,
    token_version: int = 1,
) -> str:
    import datetime

    payload = {
        "developer_id": developer_id,
        "github_username": github_username,
        "app_role": app_role,
        "token_version": token_version,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(hours=TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> AuthUser:
    token = credentials.credentials
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[JWT_ALGORITHM]
        )
    except (jwt.InvalidTokenError, KeyError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    # Check that the developer is still active and token_version matches
    from app.models.models import Developer

    developer_id = payload.get("developer_id")
    result = await db.execute(
        select(Developer.is_active, Developer.app_role, Developer.token_version).where(
            Developer.id == developer_id
        )
    )
    row = result.first()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Developer account not found",
        )
    if not row.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deactivated",
        )

    # Reject tokens issued before a role change or explicit revocation
    jwt_token_version = payload.get("token_version", 1)
    if jwt_token_version != row.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked — please log in again",
        )

    return AuthUser(
        developer_id=payload["developer_id"],
        github_username=payload["github_username"],
        app_role=row.app_role,
    )


async def require_admin(
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    if user.app_role != AppRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
