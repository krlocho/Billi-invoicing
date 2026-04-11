from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedReservation:
    reservation_id: str | None = None
    guest_name: str | None = None
    checkin_date: str | None = None
    checkout_date: str | None = None
    room_type: str | None = None
    nights: int | None = None
    gross_amount: float | None = None
    commission_amount: float | None = None
    net_amount: float | None = None
    currency: str = "EUR"
    status: str | None = None
    extra_data: dict | None = None


@dataclass
class ChannelFileResult:
    reservations: list[ParsedReservation] = field(default_factory=list)
    channel_name: str = ""
    errors: list[str] = field(default_factory=list)


class ChannelParser(ABC):
    @abstractmethod
    def parse(self, file_path: str) -> ChannelFileResult:
        ...

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        ...
