"""Build few-shot examples from manually labelled matches.

Pulls from `evaluation_labels` — the independent ground truth — so the
LLM learns the hotel's specific payout patterns (Booking with no names,
Airbnb groupings, etc.) without any feedback loop from its own past
mistakes.
"""

from __future__ import annotations

import uuid
from sqlalchemy.orm import Session

from src.models.bank_transaction import BankTransaction
from src.models.channel import Channel
from src.models.channel_reservation import ChannelReservation
from src.models.evaluation_label import EvaluationLabel


def build_examples_block(
    db: Session,
    tenant_id: uuid.UUID,
    k: int = 8,
    exclude_tx_ids: set[uuid.UUID] | None = None,
) -> str:
    """Return a compact text block of `k` confirmed match examples.

    Diversity strategy: prefer one example per (channel, group_size)
    combination so the LLM sees the full range — single Stripe payment,
    grouped Airbnb, large Booking batch, etc.
    """
    q = (
        db.query(EvaluationLabel)
        .filter(EvaluationLabel.label_type == "match")
        .order_by(EvaluationLabel.labeled_at.desc())
    )
    if exclude_tx_ids:
        q = q.filter(EvaluationLabel.bank_transaction_id.notin_(exclude_tx_ids))
    rows = q.limit(50).all()
    if not rows:
        return ""

    # Bucket by (channel_name, group_size), keep one per bucket.
    buckets: dict[tuple[str, int], EvaluationLabel] = {}
    label_channels: dict[uuid.UUID, str] = {}
    for label in rows:
        if not label.reservation_ids:
            continue
        first = (
            db.query(ChannelReservation, Channel)
            .outerjoin(Channel, ChannelReservation.channel_id == Channel.id)
            .filter(ChannelReservation.id == label.reservation_ids[0])
            .first()
        )
        if not first:
            continue
        _, ch = first
        channel_name = (ch.name if ch else "unknown") or "unknown"
        group_size = len(label.reservation_ids)
        key = (channel_name, min(group_size, 4))
        buckets.setdefault(key, label)
        label_channels[label.id] = channel_name

    chosen = list(buckets.values())[:k]
    if not chosen:
        return ""

    lines: list[str] = ["## Confirmed match examples (use these patterns):"]
    for label in chosen:
        tx = db.query(BankTransaction).filter(
            BankTransaction.id == label.bank_transaction_id
        ).first()
        if not tx:
            continue
        reservations = (
            db.query(ChannelReservation)
            .filter(ChannelReservation.id.in_(label.reservation_ids))
            .all()
        )
        if not reservations:
            continue
        channel_name = label_channels.get(label.id, "unknown")
        # Compact one-liner per example
        desc = (tx.description or "").strip().replace("\n", " ")[:60]
        res_parts: list[str] = []
        gross_sum = 0.0
        net_sum = 0.0
        for r in reservations:
            name = (r.guest_name or "").strip() or (r.reservation_id or "?")
            net = float(r.net_amount) if r.net_amount is not None else 0.0
            gross = float(r.gross_amount) if r.gross_amount is not None else 0.0
            gross_sum += gross
            net_sum += net
            res_parts.append(f"{name[:18]} (net {net:.2f})")
        amount = float(tx.amount)
        commission_pct = (
            (gross_sum - net_sum) / gross_sum * 100 if gross_sum else 0.0
        )
        lines.append(
            f"- {channel_name} {amount:.2f} «{desc}» = "
            f"{' + '.join(res_parts)}  "
            f"[gross {gross_sum:.2f}, net {net_sum:.2f}, commission {commission_pct:.1f}%]"
        )
    return "\n".join(lines) + "\n"
