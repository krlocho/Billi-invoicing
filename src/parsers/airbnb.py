"""Parser for Airbnb host transaction history CSV.

Airbnb files contain mixed row types:
  - Type="Reservation" → real reservation rows
  - Type="Payout"      → bank transfer summaries (NOT reservations)
  - Type="Resolution Adjustment", "Co-host payout", etc. → ignore

Date columns use US format (MM/DD/YYYY). Money columns:
  - "Gross earnings" → total before any deduction (gross_amount)
  - "Service fee"    → Airbnb's host fee (commission_amount)
  - "Amount"         → what gets paid to host for this reservation (net_amount)
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation

logger = logging.getLogger(__name__)

# Hallmark columns that identify an Airbnb transactions export.
AIRBNB_SIGNATURE_COLUMNS = {
    "confirmation code",
    "gross earnings",
    "paid out",
    "service fee",
    "nights",
}


def _parse_us_date(value) -> str | None:
    """Airbnb dates come as MM/DD/YYYY. Return ISO yyyy-mm-dd or None."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip().replace("€", "").replace("$", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


class AirbnbParser(ChannelParser):
    def can_parse(self, file_path: str) -> bool:
        if not file_path.lower().endswith(".csv"):
            return False
        try:
            df = pd.read_csv(file_path, nrows=1)
        except Exception:
            return False
        cols = {str(c).lower().strip().lstrip("﻿") for c in df.columns}
        return len(AIRBNB_SIGNATURE_COLUMNS & cols) >= 3

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            return ChannelFileResult(errors=[f"Failed to read Airbnb CSV: {e}"])

        # Normalise column lookup (BOM, casing, whitespace)
        col_map: dict[str, str] = {}
        for c in df.columns:
            key = str(c).lower().strip().lstrip("﻿")
            col_map[key] = c

        def col(name: str) -> str | None:
            return col_map.get(name.lower())

        type_col = col("type")
        ref_col = col("reference code")
        reservations: list[ParsedReservation] = []

        # Airbnb CSVs interleave Payout rows with their child Reservation rows
        # (Payout first, then the reservations it disbursed). The Payout row
        # carries the "Reference code" (G-…) that links siblings together.
        # We keep that ref as state and stamp it onto each subsequent
        # Reservation row until the next Payout row.
        current_payout_ref: str | None = None

        for _, row in df.iterrows():
            row_type = str(row.get(type_col, "")).strip().lower() if type_col else ""

            if row_type == "payout":
                ref = row.get(ref_col) if ref_col else None
                if ref is not None and pd.notna(ref):
                    s = str(ref).strip()
                    current_payout_ref = s or None
                else:
                    current_payout_ref = None
                continue

            if row_type and row_type != "reservation":
                # Resolution adjustments, host fees, etc. — ignore but keep the
                # current payout context in case the next row is a reservation.
                continue

            confirmation = row.get(col("confirmation code")) if col("confirmation code") else None
            guest = row.get(col("guest")) if col("guest") else None
            listing = row.get(col("listing")) if col("listing") else None

            # Skip placeholder / summary rows that lack identifying data
            if not confirmation and not guest:
                continue

            checkin = _parse_us_date(row.get(col("start date"))) if col("start date") else None
            checkout = _parse_us_date(row.get(col("end date"))) if col("end date") else None
            nights = _to_int(row.get(col("nights"))) if col("nights") else None

            gross = _to_float(row.get(col("gross earnings"))) if col("gross earnings") else None
            service_fee = _to_float(row.get(col("service fee"))) if col("service fee") else None
            net = _to_float(row.get(col("amount"))) if col("amount") else None
            currency = (
                str(row.get(col("currency"))).strip()
                if col("currency") and pd.notna(row.get(col("currency")))
                else "EUR"
            )

            reservations.append(ParsedReservation(
                reservation_id=str(confirmation).strip() if confirmation and pd.notna(confirmation) else None,
                guest_name=str(guest).strip() if guest and pd.notna(guest) else None,
                checkin_date=checkin,
                checkout_date=checkout,
                room_type=str(listing).strip() if listing and pd.notna(listing) else None,
                nights=nights,
                gross_amount=gross,
                commission_amount=service_fee,
                net_amount=net,
                currency=currency,
                status="confirmed",
                payout_ref=current_payout_ref,
                extra_data=None,
            ))

        return ChannelFileResult(reservations=reservations, channel_name="airbnb")
