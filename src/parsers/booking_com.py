import pandas as pd

from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation


class BookingComParser(ChannelParser):
    """Parser for Booking.com reservation export CSV files."""

    # Common column name variants in Booking.com exports
    COLUMN_MAPS = {
        "reservation_id": ["Reservation ID", "Booking ID", "Nº de reserva", "reservation_id"],
        "guest_name": ["Guest Name", "Nombre del huésped", "guest_name", "Nombre"],
        "checkin": ["Check-in", "Check-in Date", "Fecha de entrada", "checkin_date"],
        "checkout": ["Check-out", "Check-out Date", "Fecha de salida", "checkout_date"],
        "room_type": ["Room Type", "Tipo de habitación", "room_type"],
        "total": ["Total", "Total Price", "Precio total", "Commission Amount", "gross_amount"],
        "commission": ["Commission", "Comisión", "Commission Amount", "commission_amount"],
        "status": ["Status", "Estado", "Booking Status", "status"],
        "nights": ["Nights", "Noches", "nights"],
    }

    def can_parse(self, file_path: str) -> bool:
        try:
            df = pd.read_csv(file_path, nrows=1)
            columns_lower = {c.lower() for c in df.columns}
            # Check for Booking.com-specific columns
            booking_indicators = {"reservation id", "booking id", "nº de reserva", "guest name"}
            return bool(columns_lower & booking_indicators)
        except Exception:
            return False

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            df = pd.read_csv(file_path)
        except Exception:
            try:
                df = pd.read_excel(file_path)
            except Exception as e:
                return ChannelFileResult(channel_name="Booking.com", errors=[str(e)])

        reservations = []
        for _, row in df.iterrows():
            res = ParsedReservation(
                reservation_id=self._get_field(row, "reservation_id"),
                guest_name=self._get_field(row, "guest_name"),
                checkin_date=self._get_field(row, "checkin"),
                checkout_date=self._get_field(row, "checkout"),
                room_type=self._get_field(row, "room_type"),
                nights=self._get_int_field(row, "nights"),
                gross_amount=self._get_float_field(row, "total"),
                commission_amount=self._get_float_field(row, "commission"),
                status=self._get_field(row, "status"),
                extra_data={col: str(row[col]) for col in df.columns if pd.notna(row[col])},
            )

            # Calculate net if we have gross and commission
            if res.gross_amount and res.commission_amount:
                res.net_amount = res.gross_amount - abs(res.commission_amount)

            reservations.append(res)

        return ChannelFileResult(reservations=reservations, channel_name="Booking.com")

    def _get_field(self, row: pd.Series, field_key: str) -> str | None:
        for col_name in self.COLUMN_MAPS.get(field_key, []):
            for actual_col in row.index:
                if actual_col.lower().strip() == col_name.lower().strip():
                    val = row[actual_col]
                    if pd.notna(val):
                        return str(val).strip()
        return None

    def _get_float_field(self, row: pd.Series, field_key: str) -> float | None:
        val = self._get_field(row, field_key)
        if val:
            try:
                return float(val.replace(",", ".").replace("€", "").strip())
            except ValueError:
                return None
        return None

    def _get_int_field(self, row: pd.Series, field_key: str) -> int | None:
        val = self._get_field(row, field_key)
        if val:
            try:
                return int(float(val))
            except ValueError:
                return None
        return None
