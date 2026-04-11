import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import String, Date, DateTime, Numeric, Integer, Boolean, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class ChannelReservation(Base):
    __tablename__ = "channel_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("uploads.id"))
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    channel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("channels.id"))
    reservation_id: Mapped[str | None] = mapped_column(String(100))
    guest_name: Mapped[str | None] = mapped_column(String(255))
    checkin_date: Mapped[date | None] = mapped_column(Date)
    checkout_date: Mapped[date | None] = mapped_column(Date)
    room_type: Mapped[str | None] = mapped_column(String(100))
    nights: Mapped[int | None] = mapped_column(Integer)
    gross_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    commission_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    status: Mapped[str | None] = mapped_column(String(20))  # confirmed, cancelled, no-show
    extra_data: Mapped[dict | None] = mapped_column(JSONB)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    upload = relationship("Upload", back_populates="channel_reservations")
    channel = relationship("Channel", back_populates="reservations")
