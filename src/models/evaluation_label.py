"""Independent evaluation labels — manually-curated ground truth.

Stored separately from `reconciliation_matches` so labellers cannot
see (and cannot be influenced by) the system's predictions while
labelling. Used by `src/evaluation/runner.py` as an unbiased gold
set, in contrast to `confirmed` matches which were proposed by the
system itself.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


class EvaluationLabel(Base):
    __tablename__ = "evaluation_labels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliations.id", ondelete="CASCADE"), nullable=False
    )
    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_transactions.id", ondelete="CASCADE"), nullable=False
    )
    reservation_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # "match" → the reservations listed are the correct payout group
    # "no_match" → this bank tx is not a channel payout (mortgage, transfer, fee, ...)
    label_type: Mapped[str] = mapped_column(String(20), nullable=False)
    labeled_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    labeled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
