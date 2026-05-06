"""Three reconciliation strategies for ablation comparison.

  1. algorithmic_only — no LLM. Subset-sum on amounts (bounded, k ≤ 4)
     using the learned commission, with name similarity as tiebreaker.
  2. llm_only        — LLM proposes matches, NO algorithmic validation
     (raw LLM confidence is the score).
  3. hybrid          — current production: LLM + algorithmic validator
     with hybrid scoring (the existing run_matching).

All strategies emit MatchPrediction objects with a (bank_transaction_id,
reservation_ids, score) shape so they can be compared against ground truth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from itertools import combinations

from sqlalchemy.orm import Session

from src.matching.commission import (
    amount_matches,
    calculate_expected_net_for_group,
)
from src.matching.engine import (
    MatchResult,
    ReservationData,
    TransactionData,
    _detect_channel,
    _llm_match,
    run_matching,
)
from src.matching.fuzzy_names import name_similarity
from src.models.reconciliation import MatchReservation, ReconciliationMatch

logger = logging.getLogger(__name__)


@dataclass
class MatchPrediction:
    bank_transaction_id: str
    reservation_ids: frozenset[str]
    score: float
    strategy: str


# -- algorithmic-only baseline ------------------------------------------------

def algorithmic_only(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    commission_lookup: dict[str, dict] | None = None,
    max_group_size: int = 4,
    amount_tolerance: float = 0.05,
) -> list[MatchPrediction]:
    """Pure algorithmic matching: enumerate small subsets per channel and
    pick the one whose expected net (after learned commission) best matches
    the bank amount. No LLM."""
    commission_lookup = commission_lookup or {}
    out: list[MatchPrediction] = []
    used: set[str] = set()

    by_channel: dict[str | None, list[ReservationData]] = {}
    for r in reservations:
        by_channel.setdefault(r.channel_code, []).append(r)

    for tx in transactions:
        ch = _detect_channel(tx.description) or "booking"
        learned = commission_lookup.get(ch.lower())
        tenant_config = (
            {"learned_rate": learned["rate"], "psf_rate": learned.get("psf_rate", 0)}
            if learned
            else None
        )

        candidates = [r for r in by_channel.get(ch, []) if r.id not in used]
        if not candidates:
            candidates = [r for r in reservations if r.id not in used]

        bank_amount = abs(tx.amount)
        best: tuple[float, list[ReservationData]] | None = None

        for k in range(1, min(max_group_size, len(candidates)) + 1):
            for combo in combinations(candidates, k):
                grosses = [r.gross_amount or 0 for r in combo]
                if not all(grosses):
                    continue
                expected = calculate_expected_net_for_group(grosses, ch, tenant_config)
                ok, diff = amount_matches(bank_amount, expected, amount_tolerance)
                if not ok:
                    continue
                # name similarity as tiebreaker
                name_score = max(
                    (name_similarity(tx.description, r.guest_name or "") for r in combo),
                    default=0.0,
                )
                score = max(0.0, 1.0 - (diff / max(bank_amount, 1))) * 0.7 + name_score * 0.3
                if best is None or score > best[0]:
                    best = (score, list(combo))

        if best:
            score, combo = best
            ids = frozenset(r.id for r in combo)
            for r in combo:
                used.add(r.id)
            out.append(MatchPrediction(
                bank_transaction_id=tx.id,
                reservation_ids=ids,
                score=round(score, 4),
                strategy="algorithmic_only",
            ))

    return out


# -- LLM-only -----------------------------------------------------------------

def llm_only(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    tenant_context: str = "",
) -> list[MatchPrediction]:
    """Call the LLM and trust its predictions verbatim — no algorithmic
    validation, no name/amount cross-check.

    The engine sends 8-char id prefixes to the LLM to save tokens; the
    full-ID expansion is normally done by the validator. We replicate
    that here so the predictions are comparable to ground truth without
    re-introducing scoring logic.
    """
    detected = [_detect_channel(t.description) for t in transactions]
    raw: list[MatchResult] = _llm_match(
        transactions, reservations, detected,
        rag_context="No previous reconciliation examples available.",
        tenant_context=tenant_context,
        model_tier="fast",
    )

    tx_by_prefix = {t.id[:8]: t.id for t in transactions}
    res_by_prefix = {r.id[:8]: r.id for r in reservations}

    out: list[MatchPrediction] = []
    for m in raw:
        full_tx = tx_by_prefix.get(m.bank_transaction_id[:8])
        if not full_tx:
            continue
        full_res = [res_by_prefix.get(rid[:8]) for rid in m.reservation_ids]
        full_res = [r for r in full_res if r]
        if not full_res:
            continue
        out.append(MatchPrediction(
            bank_transaction_id=full_tx,
            reservation_ids=frozenset(full_res),
            score=float(m.confidence_score),
            strategy="llm_only",
        ))
    return out


# -- hybrid (current production) ---------------------------------------------

def hybrid(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    tenant_context: str = "",
    commission_lookup: dict[str, dict] | None = None,
) -> list[MatchPrediction]:
    matches = run_matching(
        transactions, reservations,
        feedback_examples=None,
        tenant_context=tenant_context,
        commission_lookup=commission_lookup,
    )
    return [
        MatchPrediction(
            bank_transaction_id=m.bank_transaction_id,
            reservation_ids=frozenset(m.reservation_ids),
            score=float(m.confidence_score),
            strategy="hybrid",
        )
        for m in matches
    ]


def hybrid_from_db(db: Session, reconciliation_id: str) -> list[MatchPrediction]:
    """Use the matches already produced by the production hybrid pipeline
    (stored in DB). Useful to evaluate without re-spending LLM tokens."""
    import uuid as _uuid
    rows = (
        db.query(ReconciliationMatch)
        .filter(ReconciliationMatch.reconciliation_id == _uuid.UUID(reconciliation_id))
        .all()
    )
    out: list[MatchPrediction] = []
    for m in rows:
        rids = [
            str(mr.reservation_id)
            for mr in db.query(MatchReservation)
            .filter(MatchReservation.match_id == m.id)
            .all()
        ]
        out.append(MatchPrediction(
            bank_transaction_id=str(m.bank_transaction_id),
            reservation_ids=frozenset(rids),
            score=float(m.confidence_score) if m.confidence_score is not None else 0.0,
            strategy="hybrid_from_db",
        ))
    return out
