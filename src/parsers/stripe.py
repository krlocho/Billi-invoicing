"""Parser for Stripe charge export ("Unified payments" CSV).

Stripe rows are individual charges, not stays. We map:
  reservation_id   = charge id (ch_...)
  guest_name       = Customer Email if present, else "—"
  gross_amount     = Amount
  commission_amount= Fee (Stripe processing fee)
  net_amount       = gross - fee
  checkin/out      = Created date (point-in-time payment, no stay range)
  nights           = 1 (placeholder — Stripe is a single charge, not a stay)
  room_type        = "Pago tarjeta · {Statement Descriptor}"
  status           = Stripe status (Paid, Refunded, ...)
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation

logger = logging.getLogger(__name__)

STRIPE_SIGNATURE_COLUMNS = {
    "id",
    "created date (utc)",
    "amount",
    "fee",
    "statement descriptor",
}


def _parse_amount(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().replace("€", "").replace("$", "")
    if not s:
        return None
    # Stripe localised CSV uses ',' as decimal separator
    s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") == 0 else s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_dt(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[: len(fmt) + 4], fmt).date().isoformat()
        except ValueError:
            continue
    return None


class StripeParser(ChannelParser):
    def can_parse(self, file_path: str) -> bool:
        if not file_path.lower().endswith(".csv"):
            return False
        try:
            df = pd.read_csv(file_path, nrows=1)
        except Exception:
            return False
        cols = {str(c).lower().strip().lstrip("﻿") for c in df.columns}
        return len(STRIPE_SIGNATURE_COLUMNS & cols) >= 4

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            return ChannelFileResult(errors=[f"Failed to read Stripe CSV: {e}"])

        col_map: dict[str, str] = {}
        for c in df.columns:
            key = str(c).lower().strip().lstrip("﻿")
            col_map[key] = c

        def col(name: str) -> str | None:
            return col_map.get(name.lower())

        reservations: list[ParsedReservation] = []
        for _, row in df.iterrows():
            charge_id = row.get(col("id")) if col("id") else None
            if not charge_id or pd.isna(charge_id):
                continue

            gross = _parse_amount(row.get(col("amount"))) if col("amount") else None
            fee = _parse_amount(row.get(col("fee"))) if col("fee") else None
            net = (gross - fee) if (gross is not None and fee is not None) else None

            email = row.get(col("customer email")) if col("customer email") else None
            cust_desc = row.get(col("customer description")) if col("customer description") else None
            descr = row.get(col("description")) if col("description") else None
            statement = row.get(col("statement descriptor")) if col("statement descriptor") else None

            guest = None
            for candidate in (email, cust_desc, descr):
                if candidate and pd.notna(candidate):
                    guest = str(candidate).strip()
                    if guest:
                        break

            created = _parse_dt(row.get(col("created date (utc)"))) if col("created date (utc)") else None
            currency = (
                str(row.get(col("currency"))).strip().upper()
                if col("currency") and pd.notna(row.get(col("currency")))
                else "EUR"
            )
            status_val = row.get(col("status")) if col("status") else None

            room_type = None
            if statement and pd.notna(statement):
                room_type = f"Pago tarjeta · {str(statement).strip()}"

            reservations.append(ParsedReservation(
                reservation_id=str(charge_id).strip(),
                guest_name=guest,
                checkin_date=created,
                checkout_date=created,
                room_type=room_type,
                nights=1 if created else None,
                gross_amount=gross,
                commission_amount=fee,
                net_amount=net,
                currency=currency,
                status=str(status_val).strip().lower() if status_val and pd.notna(status_val) else None,
                extra_data=None,
            ))

        return ChannelFileResult(reservations=reservations, channel_name="stripe")
