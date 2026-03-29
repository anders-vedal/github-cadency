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


def create_jwt(developer_id: int, github_username: str, app_role: str) -> str:
    import datetime

    payload = {
        "developer_id": developer_id,
        "github_username": github_username,
        "app_role": app_role,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=7),
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

    # Check that the developer is still active in the database
    from app.models.models import Developer

    developer_id = payload.get("developer_id")
    result = await db.execute(
        select(Developer.is_active).where(Developer.id == developer_id)
    )
    is_active = result.scalar_one_or_none()

    if is_active is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Developer account not found",
        )
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account has been deactivated",
        )

    return AuthUser(
        developer_id=payload["developer_id"],
        github_username=payload["github_username"],
        app_role=payload["app_role"],
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
