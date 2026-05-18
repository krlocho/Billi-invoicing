"""add_payout_ref_to_channel_reservations

Revision ID: 3a5108c49cb9
Revises: 93088b3be1b7
Create Date: 2026-05-18 11:52:47.275975
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a5108c49cb9'
down_revision: Union[str, None] = '93088b3be1b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "channel_reservations",
        sa.Column("payout_ref", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_channel_reservations_payout_ref",
        "channel_reservations",
        ["payout_ref"],
    )


def downgrade() -> None:
    op.drop_index("ix_channel_reservations_payout_ref", table_name="channel_reservations")
    op.drop_column("channel_reservations", "payout_ref")
