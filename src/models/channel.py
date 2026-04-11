import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func, ARRAY
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Booking.com"
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # "booking"
    commission_config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payment_delay_days: Mapped[int] = mapped_column(Integer, default=7)
    bank_description_patterns: Mapped[list | None] = mapped_column(ARRAY(String))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    tenant = relationship("Tenant", back_populates="channels")
    reservations = relationship("ChannelReservation", back_populates="channel")
