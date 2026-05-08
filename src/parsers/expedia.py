"""Parser for Expedia Spanish payout statement.

Columns observed:
  Tu número de referencia   (always "Información no facilitada" — useless)
  Fecha solicitada          (date of payout request)
  Estado                    (e.g. "Pagado")
  Número de seguimiento     (Expedia tracking id — use as reservation_id)
  ID de pago                (Expedia internal payment id)
  Fecha de pago             (date money lands)
  Extracto de pago          (statement reference)
  Importe procesado         ("EUR 2072.26" → parse currency + amount)

Expedia statements don't include guest name, room or stay dates.
We map "Fecha solicitada" → checkin_date and "Fecha de pago" →
checkout_date as the closest reasonable proxy for the labeller to
filter by date.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

import pandas as pd

from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation

logger = logging.getLogger(__name__)

EXPEDIA_SIGNATURE_COLUMNS = {
    "tu número de referencia",
    "número de seguimiento",
    "id de pago",
    "extracto de pago",
    "importe procesado",
}

_AMOUNT_RE = re.compile(r"([A-Z]{3})\s*([\-\d.,]+)")


def _parse_amount_with_ccy(value) -> tuple[float | None, str]:
    """Parse 'EUR 2072.26' or '2072,26' → (2072.26, 'EUR')."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None, "EUR"
    s = str(value).strip()
    m = _AMOUNT_RE.search(s)
    if m:
        ccy = m.group(1)
        num = m.group(2).replace(".", "").replace(",", ".") if m.group(2).count(",") == 1 else m.group(2).replace(",", ".")
        try:
            return float(num), ccy
        except ValueError:
            return None, ccy
    # plain number fallback
    cleaned = s.replace("€", "").replace("$", "").replace(",", ".")
    try:
        return float(cleaned), "EUR"
    except ValueError:
        return None, "EUR"


def _parse_date(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


class ExpediaParser(ChannelParser):
    def can_parse(self, file_path: str) -> bool:
        if not file_path.lower().endswith(".csv"):
            return False
        try:
            df = pd.read_csv(file_path, nrows=1)
        except Exception:
            return False
        cols = {str(c).lower().strip().lstrip("﻿") for c in df.columns}
        return len(EXPEDIA_SIGNATURE_COLUMNS & cols) >= 3

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            return ChannelFileResult(errors=[f"Failed to read Expedia CSV: {e}"])

        col_map: dict[str, str] = {}
        for c in df.columns:
            key = str(c).lower().strip().lstrip("﻿")
            col_map[key] = c

        def col(name: str) -> str | None:
            return col_map.get(name.lower())

        reservations: list[ParsedReservation] = []
        for _, row in df.iterrows():
            tracking = row.get(col("número de seguimiento")) if col("número de seguimiento") else None
            payment_id = row.get(col("id de pago")) if col("id de pago") else None
            statement = row.get(col("extracto de pago")) if col("extracto de pago") else None

            if not tracking or pd.isna(tracking):
                continue

            requested = _parse_date(row.get(col("fecha solicitada"))) if col("fecha solicitada") else None
            paid_on = _parse_date(row.get(col("fecha de pago"))) if col("fecha de pago") else None
            gross, ccy = _parse_amount_with_ccy(
                row.get(col("importe procesado")) if col("importe procesado") else None
            )

            status_val = row.get(col("estado")) if col("estado") else None

            room_type = None
            if statement and pd.notna(statement):
                room_type = f"Pago Expedia · extracto {str(statement).strip()}"

            reservations.append(ParsedReservation(
                reservation_id=str(tracking).strip(),
                guest_name=None,
                # Expedia statements lack stay dates. Use payout dates so
                # the labeller can filter by approximate timeframe.
                checkin_date=requested,
                checkout_date=paid_on,
                room_type=room_type,
                nights=None,
                gross_amount=gross,
                commission_amount=None,
                # Expedia merchant statements list the net the host actually
                # receives in "Importe procesado". So gross == net here.
                net_amount=gross,
                currency=ccy or "EUR",
                status=str(status_val).strip().lower() if status_val and pd.notna(status_val) else None,
                extra_data={"payment_id": str(payment_id).strip()} if payment_id and pd.notna(payment_id) else None,
            ))

        return ChannelFileResult(reservations=reservations, channel_name="expedia")
