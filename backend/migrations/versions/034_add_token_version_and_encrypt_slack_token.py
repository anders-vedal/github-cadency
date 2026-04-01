"""Add token_version to developers and encrypt existing Slack bot tokens.

Revision ID: 034
Revises: 033
Create Date: 2026-04-01
"""
import os

from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add token_version column to developers
    op.add_column(
        "developers",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
    )

    # Encrypt any existing plaintext Slack bot tokens
    encryption_key = os.environ.get("ENCRYPTION_KEY", "")
    if encryption_key:
        from cryptography.fernet import Fernet

        f = Fernet(encryption_key.encode())
        conn = op.get_bind()
        rows = conn.execute(
            sa.text("SELECT id, bot_token FROM slack_config WHERE bot_token IS NOT NULL")
        ).fetchall()
        for row in rows:
            # Skip if already encrypted (Fernet tokens start with 'gAAAAAB')
            if row.bot_token and not row.bot_token.startswith("gAAAAAB"):
                encrypted = f.encrypt(row.bot_token.encode()).decode()
                conn.execute(
                    sa.text("UPDATE slack_config SET bot_token = :token WHERE id = :id"),
                    {"token": encrypted, "id": row.id},
                )


def downgrade() -> None:
    op.drop_column("developers", "token_version")
    # Note: downgrade does not decrypt bot tokens — requires manual intervention
