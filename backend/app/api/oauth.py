import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import create_jwt, get_current_user
from app.config import settings
from app.logging import get_logger
from app.models.database import get_db
from app.rate_limit import limiter
from app.models.models import Developer
from app.schemas.schemas import AuthMeResponse, AuthUser

logger = get_logger(__name__)

router = APIRouter()

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

OAUTH_STATE_COOKIE = "devpulse_oauth_state"
OAUTH_STATE_MAX_AGE = 600  # 10 minutes


@router.get("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request):
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.github_client_id,
        "redirect_uri": f"{settings.frontend_url}/auth/callback",
        "scope": "read:user",
        "state": state,
    }
    response = JSONResponse(content={"url": f"{GITHUB_AUTHORIZE_URL}?{urlencode(params)}"})
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        max_age=OAUTH_STATE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=not settings.frontend_url.startswith("http://localhost"),
    )
    return response


@router.get("/auth/callback")
@limiter.limit("10/minute")
async def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    # Validate OAuth state parameter (CSRF protection)
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not cookie_state or cookie_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF attack")

    # Exchange code for GitHub access token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            json={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        if token_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="GitHub token exchange failed")

        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            error = token_data.get("error_description", "Unknown error")
            raise HTTPException(status_code=400, detail=f"GitHub OAuth error: {error}")

        # Get GitHub user info
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        if user_resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub user")

        gh_user = user_resp.json()
        github_username = gh_user["login"]

        # Gate sign-in. Priority:
        # 1. DEVPULSE_ALLOWED_USERS — explicit allowlist (preferred for User-account installations)
        # 2. GITHUB_ORG — legacy org-membership check (preserved for back-compat)
        # 3. Neither set → fail closed so a misconfigured deploy doesn't accidentally open sign-up
        allowed = settings.allowed_users_list
        if allowed:
            if github_username.lower() not in allowed:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: {github_username} is not in DEVPULSE_ALLOWED_USERS",
                )
        elif settings.github_org:
            org_resp = await client.get(
                f"https://api.github.com/orgs/{settings.github_org}/members/{github_username}",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if org_resp.status_code == 404:
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied: {github_username} is not a member of the {settings.github_org} organization",
                )
        else:
            raise HTTPException(
                status_code=403,
                detail="Sign-in is not configured: set DEVPULSE_ALLOWED_USERS (comma-separated GitHub usernames) or GITHUB_ORG.",
            )

    avatar_url = gh_user.get("avatar_url")
    display_name = gh_user.get("name") or github_username

    # Lookup or create developer
    result = await db.execute(
        select(Developer).where(Developer.github_username == github_username)
    )
    dev = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if dev is None:
        # Determine role: initial admin (only if no admin exists yet) or regular developer
        app_role = "developer"
        if (
            settings.devpulse_initial_admin
            and github_username.lower() == settings.devpulse_initial_admin.lower()
        ):
            existing_admin = (await db.execute(
                select(Developer).where(Developer.app_role == "admin").limit(1)
            )).scalar_one_or_none()
            if existing_admin is None:
                app_role = "admin"
                logger.warning(
                    "Initial admin granted",
                    username=github_username,
                    event_type="system.config",
                )
            else:
                logger.info(
                    "Initial admin env var ignored — admin already exists",
                    username=github_username,
                    existing_admin=existing_admin.github_username,
                    event_type="system.config",
                )

        dev = Developer(
            github_username=github_username,
            display_name=display_name,
            avatar_url=avatar_url,
            app_role=app_role,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        db.add(dev)
        await db.commit()
        await db.refresh(dev)
    else:
        if not dev.is_active:
            raise HTTPException(status_code=403, detail="Account is deactivated")
        dev.avatar_url = avatar_url
        dev.updated_at = now
        await db.commit()
        await db.refresh(dev)

    # Issue JWT
    token = create_jwt(dev.id, dev.github_username, dev.app_role, dev.token_version)

    # Redirect to frontend with token in URL fragment (not query param)
    # Fragments are never sent to servers or included in referrer headers
    response = RedirectResponse(
        url=f"{settings.frontend_url}/auth/callback#token={token}",
        status_code=302,
    )
    # Clear the state cookie after successful validation
    response.delete_cookie(key=OAUTH_STATE_COOKIE)
    return response


@router.get("/auth/me", response_model=AuthMeResponse)
async def me(
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dev = await db.get(Developer, user.developer_id)
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return AuthMeResponse(
        developer_id=dev.id,
        github_username=dev.github_username,
        display_name=dev.display_name,
        app_role=dev.app_role,
        avatar_url=dev.avatar_url,
    )
