import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, Integer, DateTime, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Reconciliation(Base):
    __tablename__ = "reconciliations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    bank_upload_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("uploads.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_transactions: Mapped[int | None] = mapped_column(Integer)
    matched_auto: Mapped[int] = mapped_column(Integer, default=0)
    matched_manual: Mapped[int] = mapped_column(Integer, default=0)
    unmatched: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    matches = relationship("ReconciliationMatch", back_populates="reconciliation")


class ReconciliationMatch(Base):
    __tablename__ = "reconciliation_matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reconciliation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliations.id")
    )
    bank_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bank_transactions.id")
    )
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    confidence_tier: Mapped[str | None] = mapped_column(String(10))  # HIGH, MEDIUM, LOW
    amount_difference: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    match_type: Mapped[str | None] = mapped_column(String(20))  # auto, manual, llm_assisted
    status: Mapped[str] = mapped_column(String(20), default="pending")
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    match_details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    reconciliation = relationship("Reconciliation", back_populates="matches")
    bank_transaction = relationship("BankTransaction")
    reservations = relationship(
        "ChannelReservation", secondary="match_reservations", backref="matches"
    )


class MatchReservation(Base):
    __tablename__ = "match_reservations"

    match_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reconciliation_matches.id"), primary_key=True
    )
    reservation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channel_reservations.id"), primary_key=True
    )
