"""Seed E2E database and output JWT tokens for Playwright global setup.

Usage (from repo root):
    DATABASE_URL=postgresql+asyncpg://... JWT_SECRET=... python -m scripts.e2e_seed

Outputs JSON to stdout:
    {"admin_token": "<jwt>", "developer_token": "<jwt>"}
"""

import asyncio
import json
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# DATABASE_URL must point at the E2E database before importing app.config
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://devpulse:devpulse@localhost:5434/devpulse_e2e")

from app.api.auth import create_jwt
from app.models.database import Base
from app.models.models import Developer, RoleDefinition, Team


async def seed() -> dict:
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with SessionLocal() as db:
        # Upsert Team
        team_result = await db.execute(select(Team).where(Team.name == "e2e-team"))
        team = team_result.scalar_one_or_none()
        if not team:
            team = Team(name="e2e-team", display_order=0)
            db.add(team)
            await db.flush()

        # Upsert RoleDefinition
        role_result = await db.execute(select(RoleDefinition).where(RoleDefinition.role_key == "engineer"))
        role_def = role_result.scalar_one_or_none()
        if not role_def:
            role_def = RoleDefinition(
                role_key="engineer",
                display_name="Engineer",
                contribution_category="code_contributor",
                display_order=0,
                is_default=True,
            )
            db.add(role_def)
            await db.flush()

        # Upsert admin developer
        admin_result = await db.execute(select(Developer).where(Developer.github_username == "e2e-admin"))
        admin = admin_result.scalar_one_or_none()
        if not admin:
            admin = Developer(
                github_username="e2e-admin",
                display_name="E2E Admin",
                app_role="admin",
                team="e2e-team",
                role="engineer",
                token_version=1,
                is_active=True,
            )
            db.add(admin)
        else:
            admin.app_role = "admin"
            admin.is_active = True
        await db.flush()

        # Upsert regular developer
        dev_result = await db.execute(select(Developer).where(Developer.github_username == "e2e-dev"))
        dev = dev_result.scalar_one_or_none()
        if not dev:
            dev = Developer(
                github_username="e2e-dev",
                display_name="E2E Developer",
                app_role="developer",
                team="e2e-team",
                role="engineer",
                token_version=1,
                is_active=True,
            )
            db.add(dev)
        else:
            dev.app_role = "developer"
            dev.is_active = True
        await db.flush()

        await db.commit()

        admin_token = create_jwt(
            developer_id=admin.id,
            github_username=admin.github_username,
            app_role=admin.app_role,
            token_version=admin.token_version,
        )
        dev_token = create_jwt(
            developer_id=dev.id,
            github_username=dev.github_username,
            app_role=dev.app_role,
            token_version=dev.token_version,
        )

    await engine.dispose()
    return {"admin_token": admin_token, "developer_token": dev_token}


if __name__ == "__main__":
    result = asyncio.run(seed())
    print(json.dumps(result))
