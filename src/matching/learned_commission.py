"""Learn channel commission rates from confirmed matches.

The effective commission rate for a (tenant × channel) pair depends on
the host's account configuration (Airbnb host-only vs split, Booking
program tier, negotiated rate, etc.). Instead of asking the user to
configure it per channel/property, we infer it from observed data:

    learned_rate = 1 - (sum of bank_amounts / sum of gross_amounts)

across all confirmed matches. The result is persisted to
`channel.commission_config['learned_rate']` and used as the prior for
both the algorithmic validator and the LLM prompt.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm.attributes import flag_modified

from src.models.bank_transaction import BankTransaction
from src.models.channel import Channel
from src.models.channel_reservation import ChannelReservation
from src.models.reconciliation import MatchReservation, ReconciliationMatch

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

MIN_SAMPLES = 3


def compute_learned_commission(
    db: "Session", tenant_id, channel_id
) -> dict | None:
    """Aggregate confirmed matches for a (tenant, channel) and return the observed commission.

    Returns dict with keys: rate, sample_size, total_gross, total_bank — or None
    if there are fewer than MIN_SAMPLES confirmed matches with usable data.
    """
    rows = (
        db.query(BankTransaction, ChannelReservation)
        .join(ReconciliationMatch, ReconciliationMatch.bank_transaction_id == BankTransaction.id)
        .join(MatchReservation, MatchReservation.match_id == ReconciliationMatch.id)
        .join(ChannelReservation, ChannelReservation.id == MatchReservation.reservation_id)
        .filter(
            ReconciliationMatch.status == "confirmed",
            BankTransaction.tenant_id == tenant_id,
            ChannelReservation.channel_id == channel_id,
            ChannelReservation.gross_amount.isnot(None),
        )
        .all()
    )

    by_match: dict = {}
    for tx, res in rows:
        entry = by_match.setdefault(tx.id, {"bank_amount": float(abs(tx.amount)), "gross": 0.0})
        entry["gross"] += float(res.gross_amount or 0)

    usable = [v for v in by_match.values() if v["gross"] > 0]
    if len(usable) < MIN_SAMPLES:
        return None

    total_bank = sum(v["bank_amount"] for v in usable)
    total_gross = sum(v["gross"] for v in usable)
    if total_gross <= 0:
        return None

    rate = max(0.0, min(1.0, 1.0 - (total_bank / total_gross)))
    return {
        "rate": round(rate, 4),
        "sample_size": len(usable),
        "total_gross": round(total_gross, 2),
        "total_bank": round(total_bank, 2),
    }


def update_channel_learned_commission(db: "Session", tenant_id, channel_id) -> dict | None:
    """Recompute and persist the learned commission for a channel."""
    learned = compute_learned_commission(db, tenant_id, channel_id)
    if learned is None:
        return None

    channel = db.query(Channel).filter(Channel.id == channel_id).first()
    if not channel:
        return None

    config = dict(channel.commission_config or {})
    config["learned_rate"] = learned["rate"]
    config["learned_sample_size"] = learned["sample_size"]
    config["learned_at"] = datetime.now(timezone.utc).isoformat()
    channel.commission_config = config
    flag_modified(channel, "commission_config")
    db.add(channel)
    return learned


def learned_rate_lookup(db: "Session", tenant_id) -> dict[str, dict]:
    """Return {channel_code: {rate, sample_size}} for every channel in the tenant
    that has either a learned or configured commission, plus any tenant overrides.
    """
    channels = db.query(Channel).filter(Channel.tenant_id == tenant_id).all()
    out: dict[str, dict] = {}
    for ch in channels:
        cfg = ch.commission_config or {}
        rate = cfg.get("learned_rate") or cfg.get("base_rate")
        if rate is None:
            continue
        out[ch.code.lower()] = {
            "rate": float(rate),
            "sample_size": int(cfg.get("learned_sample_size", 0)),
            "is_learned": "learned_rate" in cfg,
            "psf_rate": float(cfg.get("psf_rate", 0)) if cfg.get("psf_rate") else 0.0,
        }
    return out
