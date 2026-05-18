"""Parser for Booking.com payout CSV.

The real CSV from Booking has two row types under `Type/Transaction type`:

  - `(Payout)`: one row per bank transfer to the host. Carries
    `Statement Descriptor` — the same 16-char reference that lands in
    the bank as `Concepto No.<ref>/id.<property>`. No reservations on
    this row, only the bank-deposit total.
  - `Reservation`: one row per individual reservation included in a
    payout. Shares `Statement Descriptor` with its `(Payout)` row so we
    can group them back together deterministically.

We only emit `Reservation` rows (with `payout_ref` filled in) — the
`(Payout)` rows are redundant once their children carry the same ref.
"""

from __future__ import annotations

import logging

import pandas as pd

from src.parsers.base import ChannelFileResult, ChannelParser, ParsedReservation

logger = logging.getLogger(__name__)

BOOKING_SIGNATURE_COLUMNS = {
    "type/transaction type",
    "statement descriptor",
    "property id",
    "payout amount",
    "payable amount",
}


def _norm_cols(df: pd.DataFrame) -> dict[str, str]:
    """Return lowercased-trimmed → actual-column map for resilient lookup."""
    return {str(c).lower().strip(): c for c in df.columns}


def _parse_iso_date(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s == "-":
        return None
    # Booking CSV uses YYYY-MM-DD already; isoformat-safe slice.
    return s[:10]


def _to_float(value) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s == "-":
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _to_int(value) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


class BookingComParser(ChannelParser):
    """Parser for Booking.com `Payout_from_*` CSV exports."""

    def can_parse(self, file_path: str) -> bool:
        try:
            df = pd.read_csv(file_path, nrows=1)
        except Exception:
            try:
                df = pd.read_excel(file_path, nrows=1)
            except Exception:
                return False
        cols = {str(c).lower().strip() for c in df.columns}
        # Need ≥3 of the signature columns to be confident.
        return len(BOOKING_SIGNATURE_COLUMNS & cols) >= 3

    def parse(self, file_path: str) -> ChannelFileResult:
        try:
            df = pd.read_csv(file_path)
        except Exception:
            try:
                df = pd.read_excel(file_path)
            except Exception as e:
                return ChannelFileResult(channel_name="Booking.com", errors=[str(e)])

        cols = _norm_cols(df)

        def col(name: str) -> str | None:
            return cols.get(name.lower())

        type_col = col("Type/Transaction type") or col("Type")
        descriptor_col = col("Statement Descriptor")
        ref_col = col("Reference number")
        checkin_col = col("Check-in date")
        checkout_col = col("Check-out date")
        status_col = col("Reservation status")
        rooms_col = col("Rooms") or col("Room nights")
        nights_col = col("Room nights")
        property_col = col("Property name")
        gross_col = col("Transaction amount") or col("Gross amount")
        commission_col = col("Commission")
        psf_col = col("Payments Service Fee")
        payable_col = col("Payable amount")
        currency_col = col("Transaction currency") or col("Payout currency")

        if not type_col:
            return ChannelFileResult(
                channel_name="Booking.com",
                errors=["Missing 'Type/Transaction type' column — not a Booking payout CSV"],
            )

        reservations: list[ParsedReservation] = []
        for _, row in df.iterrows():
            row_type = str(row.get(type_col, "")).strip()
            if row_type != "Reservation":
                continue  # (Payout) rows are summaries — skip, info is in children

            reservation_id = (
                str(row.get(ref_col)).strip() if ref_col and pd.notna(row.get(ref_col)) else None
            )
            if not reservation_id or reservation_id == "-":
                continue

            payout_ref = None
            if descriptor_col and pd.notna(row.get(descriptor_col)):
                payout_ref = str(row.get(descriptor_col)).strip().lower() or None

            gross = _to_float(row.get(gross_col)) if gross_col else None
            commission_raw = _to_float(row.get(commission_col)) if commission_col else None
            commission = abs(commission_raw) if commission_raw is not None else None
            psf = _to_float(row.get(psf_col)) if psf_col else None
            psf_abs = abs(psf) if psf is not None else 0.0
            payable = _to_float(row.get(payable_col)) if payable_col else None
            # net = exactly the amount the host receives for this reservation
            net = payable
            if net is None and gross is not None:
                net = gross - (commission or 0) - psf_abs

            reservations.append(ParsedReservation(
                reservation_id=reservation_id,
                guest_name=None,  # Booking payout CSV never exposes guest names
                checkin_date=_parse_iso_date(row.get(checkin_col)) if checkin_col else None,
                checkout_date=_parse_iso_date(row.get(checkout_col)) if checkout_col else None,
                room_type=(str(row.get(property_col)).strip() if property_col and pd.notna(row.get(property_col)) else None),
                nights=_to_int(row.get(nights_col)) if nights_col else None,
                gross_amount=gross,
                commission_amount=commission,
                net_amount=net,
                currency=(str(row.get(currency_col)).strip().upper() if currency_col and pd.notna(row.get(currency_col)) else "EUR"),
                status=(str(row.get(status_col)).strip().lower() if status_col and pd.notna(row.get(status_col)) else None),
                payout_ref=payout_ref,
                extra_data={"rooms": _to_int(row.get(rooms_col)) if rooms_col else None} if rooms_col else None,
            ))

        return ChannelFileResult(reservations=reservations, channel_name="Booking.com")
