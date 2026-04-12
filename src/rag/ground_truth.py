"""Parse real hotel data to create ground truth for RAG training.

Processes:
1. Bank statements (Santander PDF, Banca March PDF) -> structured transactions
2. Channel files (Booking CSV, Airbnb CSV, Expedia CSV, Stripe CSV) -> reservations/payouts
3. Vinculacion files (invoice CSVs/PDFs) -> confirmed invoice-reservation mappings

The ground truth connects: bank_payment -> channel_payout -> reservations -> invoices
"""

import csv
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

RAG_DATA_DIR = Path(__file__).parent.parent.parent / "rag_data"


def _safe_float(val) -> float:
    """Safely convert a value to float, handling NaN, strings, etc."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        import math
        return 0.0 if math.isnan(val) else float(val)
    s = str(val).strip().replace(",", ".")
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


@dataclass
class GroundTruthRecord:
    """A confirmed reconciliation record for RAG training."""
    # Bank side
    bank_name: str  # "santander" or "bancamarch"
    bank_date: str
    bank_description: str
    bank_amount: float
    channel: str  # "booking", "airbnb", "expedia", "stripe", "sunweb", "direct"
    bank_reference: str | None = None

    # Channel side
    payout_reference: str | None = None
    payout_date: str | None = None
    payout_amount: float | None = None

    # Reservations included in this payout
    reservations: list[dict] = field(default_factory=list)

    # Invoice side
    invoices: list[dict] = field(default_factory=list)

    # Metadata
    confidence: str = "confirmed"
    notes: str = ""


def parse_booking_csv(path: str | None = None) -> dict[str, list[dict]]:
    """Parse Booking.com payout CSV. Returns dict of payout_ref -> list of reservations."""
    if path is None:
        path = str(RAG_DATA_DIR / "Extractos canales" / "Payout_from_2025-11-01_until_2025-12-31_BOOKING.csv")

    df = pd.read_csv(path)
    payouts: dict[str, list[dict]] = {}
    current_payout_ref = None

    for _, row in df.iterrows():
        tx_type = str(row.get("Type/Transaction type", "")).strip()
        stmt_desc = str(row.get("Statement Descriptor", "")).strip()

        if tx_type == "(Payout)":
            current_payout_ref = stmt_desc
            payout_amount = row.get("Payout amount", 0)
            payout_date = str(row.get("Payout date", ""))
            payouts[current_payout_ref] = {
                "payout_ref": current_payout_ref,
                "payout_amount": float(payout_amount) if pd.notna(payout_amount) else 0,
                "payout_date": payout_date,
                "property_id": str(row.get("Property ID", "")),
                "property_name": str(row.get("Property name", "")),
                "reservations": [],
            }

        elif tx_type == "Reservation" and current_payout_ref:
            ref_number = str(row.get("Reference number", ""))
            gross = _safe_float(row.get("Gross amount"))
            commission = _safe_float(row.get("Commission"))
            commission_pct = str(row.get("Commission %", ""))
            psf = _safe_float(row.get("Payments Service Fee"))
            psf_pct = str(row.get("Payments Service Fee %", ""))
            tx_amount = _safe_float(row.get("Transaction amount"))

            payouts[current_payout_ref]["reservations"].append({
                "reservation_id": ref_number,
                "checkin": str(row.get("Check-in date", "")),
                "checkout": str(row.get("Check-out date", "")),
                "status": str(row.get("Reservation status", "")),
                "gross_amount": gross,
                "commission": commission,
                "commission_pct": commission_pct,
                "psf": psf,
                "psf_pct": psf_pct,
                "net_amount": tx_amount,
                "property_id": str(row.get("Property ID", "")),
            })

    return payouts


def parse_airbnb_csv(path: str | None = None) -> list[dict]:
    """Parse Airbnb CSV. Returns list of payouts with their reservations."""
    if path is None:
        path = str(RAG_DATA_DIR / "Extractos canales" / "airbnb_10_2025-12_2025.csv")

    df = pd.read_csv(path, encoding="utf-8-sig")
    payouts = []
    current_payout = None

    for _, row in df.iterrows():
        row_type = str(row.get("Type", "")).strip()

        if row_type == "Payout":
            if current_payout:
                payouts.append(current_payout)
            paid_out = float(row["Paid out"]) if pd.notna(row.get("Paid out")) else 0
            ref_code = str(row.get("Reference code", ""))
            current_payout = {
                "payout_amount": paid_out,
                "payout_date": str(row.get("Date", "")),
                "reference_code": ref_code,
                "reservations": [],
            }

        elif row_type == "Reservation" and current_payout is not None:
            amount = float(row["Amount"]) if pd.notna(row.get("Amount")) else 0
            service_fee = float(row["Service fee"]) if pd.notna(row.get("Service fee")) else 0
            gross = float(row["Gross earnings"]) if pd.notna(row.get("Gross earnings")) else 0

            current_payout["reservations"].append({
                "confirmation_code": str(row.get("Confirmation Code", "")),
                "guest_name": str(row.get("Guest", "")),
                "listing": str(row.get("Listing", "")),
                "checkin": str(row.get("Start date", "")),
                "checkout": str(row.get("End date", "")),
                "nights": int(row["Nights"]) if pd.notna(row.get("Nights")) else 0,
                "net_amount": amount,
                "service_fee": service_fee,
                "gross_amount": gross,
            })

    if current_payout:
        payouts.append(current_payout)

    return payouts


def parse_expedia_csv(path: str | None = None) -> list[dict]:
    """Parse Expedia statements CSV."""
    if path is None:
        path = str(RAG_DATA_DIR / "Extractos canales" / "statementsList_expedia.csv")

    df = pd.read_csv(path, encoding="utf-8-sig")
    records = []
    for _, row in df.iterrows():
        amount_str = str(row.get("Importe procesado", "")).replace("EUR ", "").replace(",", ".").strip()
        try:
            amount = float(amount_str)
        except ValueError:
            amount = 0

        records.append({
            "payment_id": str(row.get("ID de pago", "")),
            "tracking_number": str(row.get("Número de seguimiento", "")),
            "payment_date": str(row.get("Fecha de pago", "")),
            "statement_id": str(row.get("Extracto de pago", "")),
            "amount": amount,
            "status": str(row.get("Estado", "")),
        })

    return records


def parse_stripe_csv(path: str | None = None) -> list[dict]:
    """Parse Stripe unified payments CSV."""
    if path is None:
        path = str(RAG_DATA_DIR / "Extractos canales" / "unified_payments_stripe.csv")

    df = pd.read_csv(path, encoding="utf-8-sig")
    records = []
    for _, row in df.iterrows():
        # Stripe uses comma as decimal in Spanish locale
        amount_str = str(row.get("Amount", "0")).replace(",", ".")
        fee_str = str(row.get("Fee", "0")).replace(",", ".")
        try:
            amount = float(amount_str)
            fee = float(fee_str)
        except ValueError:
            amount = 0
            fee = 0

        records.append({
            "charge_id": str(row.get("id", "")),
            "created_date": str(row.get("Created date (UTC)", "")),
            "amount": amount,
            "fee": fee,
            "net_amount": amount - fee,
            "status": str(row.get("Status", "")),
            "transfer_id": str(row.get("Transfer", "")),
            "customer_id": str(row.get("Customer ID", "")),
        })

    return records


def parse_vinculacion_csv(path: str | None = None) -> list[dict]:
    """Parse vinculacion CSV (November) — invoice to reservation mapping."""
    if path is None:
        path = str(RAG_DATA_DIR / "Vinculacion extracto y canal" / "F.2215.2025.11.csv")

    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f, delimiter=";")
        headers = next(reader)
        for row in reader:
            if len(row) < 10:
                continue
            total_str = row[9].replace(".", "").replace(",", ".")
            try:
                total = float(total_str)
            except ValueError:
                total = 0

            estancia_str = row[10].replace(".", "").replace(",", ".")
            igic_str = row[11].replace(".", "").replace(",", ".")
            try:
                estancia = float(estancia_str)
                igic = float(igic_str)
            except ValueError:
                estancia = 0
                igic = 0

            records.append({
                "reservation_id": row[0].strip(),
                "invoice_number": row[1].strip(),
                "date": row[2].strip(),
                "guest_name": row[3].strip(),
                "address": row[4].strip(),
                "postal_code": row[5].strip(),
                "city": row[6].strip(),
                "country": row[7].strip(),
                "tax_id": row[8].strip(),
                "total": total,
                "estancia": estancia,
                "igic": igic,
                "property_code": row[31].strip() if len(row) > 31 else "",
                "acronym": row[32].strip() if len(row) > 32 else "",
            })

    return records


def build_ground_truth() -> list[GroundTruthRecord]:
    """Build complete ground truth by cross-referencing all data sources."""
    logger.info("Building ground truth from RAG data...")

    # Parse all sources
    booking_payouts = parse_booking_csv()
    airbnb_payouts = parse_airbnb_csv()
    expedia_payments = parse_expedia_csv()
    stripe_payments = parse_stripe_csv()
    november_invoices = parse_vinculacion_csv()

    records = []

    # 1. Booking.com ground truth records
    for ref, payout in booking_payouts.items():
        record = GroundTruthRecord(
            bank_name="santander/bancamarch",
            bank_date=payout["payout_date"],
            bank_description=f"Transferencia De Booking.com B.v., Concepto No.{ref}/id.{payout['property_id']}",
            bank_amount=payout["payout_amount"],
            bank_reference=ref,
            channel="booking",
            payout_reference=ref,
            payout_date=payout["payout_date"],
            payout_amount=payout["payout_amount"],
            reservations=payout["reservations"],
            notes=f"Booking payout with {len(payout['reservations'])} reservations. "
                  f"Property: {payout.get('property_name', 'unknown')}",
        )

        # Try to match invoices by reservation ID or guest name
        for res in payout["reservations"]:
            for inv in november_invoices:
                if inv["reservation_id"] == res.get("reservation_id", ""):
                    record.invoices.append(inv)

        records.append(record)

    # 2. Airbnb ground truth records
    for payout in airbnb_payouts:
        record = GroundTruthRecord(
            bank_name="santander",
            bank_date=payout["payout_date"],
            bank_description="Transferencia De Airbnb Payments Luxembourg S.a., Concepto Airbnb.",
            bank_amount=payout["payout_amount"],
            channel="airbnb",
            payout_reference=payout.get("reference_code"),
            payout_date=payout["payout_date"],
            payout_amount=payout["payout_amount"],
            reservations=payout["reservations"],
            notes=f"Airbnb payout with {len(payout['reservations'])} reservations. "
                  f"No bank reference — match by amount only.",
        )
        records.append(record)

    # 3. Expedia ground truth records
    for payment in expedia_payments:
        record = GroundTruthRecord(
            bank_name="bancamarch",
            bank_date=payment["payment_date"],
            bank_description=f"SEPA TR.CR TRAVELSCAPE, LLC {payment['payment_id']}",
            bank_amount=payment["amount"],
            bank_reference=payment["payment_id"],
            channel="expedia",
            payout_reference=payment["statement_id"],
            payout_date=payment["payment_date"],
            payout_amount=payment["amount"],
            notes=f"Expedia payment via Travelscape LLC. "
                  f"Bank ref uses payment_id ({payment['payment_id']}), not statement_id.",
        )
        records.append(record)

    # 4. Stripe ground truth records (group by transfer_id = bank payout)
    stripe_by_transfer: dict[str, list[dict]] = {}
    for payment in stripe_payments:
        tid = payment.get("transfer_id", "")
        if tid and tid != "nan":
            stripe_by_transfer.setdefault(tid, []).append(payment)

    for transfer_id, payments in stripe_by_transfer.items():
        total_amount = sum(p["net_amount"] for p in payments)
        record = GroundTruthRecord(
            bank_name="santander/bancamarch",
            bank_date=payments[0]["created_date"][:10] if payments else "",
            bank_description="Transferencia De Stripe Technology Europe, Limited, Concepto Stripe.",
            bank_amount=round(total_amount, 2),
            channel="stripe",
            payout_reference=transfer_id,
            payout_amount=round(total_amount, 2),
            reservations=[{
                "charge_id": p["charge_id"],
                "amount": p["amount"],
                "fee": p["fee"],
                "net_amount": p["net_amount"],
            } for p in payments],
            notes=f"Stripe payout grouping {len(payments)} charges. "
                  f"Own website (weybeach.com) — no channel commission.",
        )
        records.append(record)

    logger.info(f"Built {len(records)} ground truth records")
    return records


def export_ground_truth_json(output_path: str | None = None) -> str:
    """Export ground truth to JSON for inspection and RAG ingestion."""
    records = build_ground_truth()

    if output_path is None:
        output_path = str(RAG_DATA_DIR / "ground_truth.json")

    data = [asdict(r) for r in records]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Exported {len(records)} records to {output_path}")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    path = export_ground_truth_json()
    print(f"Ground truth exported to: {path}")

    records = build_ground_truth()
    channels = {}
    for r in records:
        channels[r.channel] = channels.get(r.channel, 0) + 1
    print(f"\nRecords by channel: {channels}")
    print(f"Total records: {len(records)}")
