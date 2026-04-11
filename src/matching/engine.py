"""Core reconciliation engine — LLM-first approach.

The LLM is the primary brain for matching bank transactions to channel reservations.
Algorithmic validation (subset-sum, fuzzy matching) acts as a verification layer.
"""

import json
import logging
from dataclasses import dataclass, field

from src.config import settings
from src.matching.commission import amount_matches, calculate_expected_net_for_group
from src.matching.fuzzy_names import name_similarity

logger = logging.getLogger(__name__)


@dataclass
class TransactionData:
    id: str
    date: str
    description: str
    amount: float


@dataclass
class ReservationData:
    id: str
    reservation_id: str | None
    guest_name: str | None
    checkin_date: str | None
    checkout_date: str | None
    gross_amount: float | None
    net_amount: float | None
    channel_code: str | None


@dataclass
class MatchResult:
    bank_transaction_id: str
    reservation_ids: list[str]
    confidence_score: float
    confidence_tier: str  # HIGH, MEDIUM, LOW
    amount_difference: float
    match_type: str  # llm, hybrid, algorithmic
    reasoning: str
    details: dict = field(default_factory=dict)


LLM_MATCHING_PROMPT = """Eres un experto en conciliación bancaria hotelera. Tu tarea es emparejar
transacciones bancarias con reservas de canales (Booking.com, Expedia, etc.).

## Reglas clave:
1. Un pago bancario de un canal puede corresponder a MÚLTIPLES reservas (pago agrupado)
2. El importe del pago = suma de importes de reservas MENOS la comisión del canal
3. Comisiones típicas: Booking.com ~15-18%, Expedia ~15-25%, Hotelbeds ~20%
4. Los nombres pueden no coincidir: "Jose" en la reserva puede ser "Francisco" en el banco
5. Los channels suelen pagar 1-15 días después del checkout
6. La descripción bancaria puede incluir el nombre del canal (ej: "BOOKING.COM BV")

## Datos del feedback histórico (ejemplos de matches confirmados):
{feedback_examples}

## Transacciones bancarias a conciliar:
{transactions_json}

## Reservas disponibles (no conciliadas):
{reservations_json}

## Instrucciones:
Analiza cada transacción bancaria e intenta emparejarla con una o más reservas.
Para cada match, explica tu razonamiento.

Responde SOLO con JSON válido:
{{
    "matches": [
        {{
            "bank_transaction_id": "uuid",
            "reservation_ids": ["uuid1", "uuid2"],
            "confidence": 0.92,
            "reasoning": "Explicación detallada del match",
            "detected_channel": "booking.com",
            "estimated_commission_rate": 0.15
        }}
    ],
    "unmatched_transactions": ["uuid1"],
    "unmatched_reservations": ["uuid1", "uuid2"],
    "analysis_notes": "Observaciones generales sobre los datos"
}}"""


def run_matching(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    feedback_examples: list[dict] | None = None,
) -> list[MatchResult]:
    """Run LLM-first matching with algorithmic validation."""

    if not transactions or not reservations:
        return []

    # Step 1: LLM matching
    llm_matches = _llm_match(transactions, reservations, feedback_examples or [])

    # Step 2: Algorithmic validation of LLM results
    validated_matches = []
    for match in llm_matches:
        validated = _validate_match(match, transactions, reservations)
        validated_matches.append(validated)

    return validated_matches


def _llm_match(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    feedback_examples: list[dict],
) -> list[MatchResult]:
    """Use LLM as the primary matching engine."""

    tx_data = [
        {"id": t.id, "date": t.date, "description": t.description, "amount": t.amount}
        for t in transactions
    ]

    res_data = [
        {
            "id": r.id,
            "reservation_id": r.reservation_id,
            "guest_name": r.guest_name,
            "checkin": r.checkin_date,
            "checkout": r.checkout_date,
            "gross_amount": r.gross_amount,
            "net_amount": r.net_amount,
            "channel": r.channel_code,
        }
        for r in reservations
    ]

    feedback_str = "Ninguno disponible aún." if not feedback_examples else json.dumps(
        feedback_examples[:10], ensure_ascii=False, indent=2
    )

    prompt = LLM_MATCHING_PROMPT.format(
        feedback_examples=feedback_str,
        transactions_json=json.dumps(tx_data, ensure_ascii=False, indent=2),
        reservations_json=json.dumps(res_data, ensure_ascii=False, indent=2),
    )

    try:
        response_text = _call_llm(prompt)
        return _parse_matching_response(response_text)
    except Exception as e:
        logger.error(f"LLM matching failed: {e}")
        return []


def _call_llm(prompt: str) -> str:
    """Call the configured LLM provider."""
    if settings.default_llm_provider == "anthropic" and settings.anthropic_api_key:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.default_llm_model,
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    elif settings.openai_api_key:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content
    else:
        raise RuntimeError("No LLM API key configured")


def _parse_matching_response(response_text: str) -> list[MatchResult]:
    """Parse LLM response into MatchResult objects."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(response_text[start:end])
        else:
            return []

    matches = []
    for m in data.get("matches", []):
        confidence = float(m.get("confidence", 0))
        tier = "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.60 else "LOW"

        matches.append(
            MatchResult(
                bank_transaction_id=m["bank_transaction_id"],
                reservation_ids=m.get("reservation_ids", []),
                confidence_score=confidence,
                confidence_tier=tier,
                amount_difference=0,  # Will be calculated in validation
                match_type="llm",
                reasoning=m.get("reasoning", ""),
                details={
                    "detected_channel": m.get("detected_channel"),
                    "estimated_commission_rate": m.get("estimated_commission_rate"),
                    "llm_confidence": confidence,
                },
            )
        )

    return matches


def _validate_match(
    match: MatchResult,
    transactions: list[TransactionData],
    reservations: list[ReservationData],
) -> MatchResult:
    """Validate and adjust LLM match with algorithmic checks."""

    # Find the transaction
    tx = next((t for t in transactions if t.id == match.bank_transaction_id), None)
    if not tx:
        match.confidence_score = 0
        match.confidence_tier = "LOW"
        return match

    # Find matched reservations
    matched_res = [r for r in reservations if r.id in match.reservation_ids]
    if not matched_res:
        match.confidence_score = 0
        match.confidence_tier = "LOW"
        return match

    # Algorithmic validation scores
    scores = {}

    # 1. Amount validation (with commission)
    channel_code = match.details.get("detected_channel", "booking.com")
    gross_amounts = [r.gross_amount or 0 for r in matched_res]
    expected_net = calculate_expected_net_for_group(gross_amounts, channel_code)
    amount_ok, amount_diff = amount_matches(abs(tx.amount), expected_net)
    match.amount_difference = amount_diff
    scores["amount"] = 1.0 if amount_ok else max(0, 1 - (amount_diff / max(abs(tx.amount), 1)))

    # 2. Name similarity (compare bank description vs guest names)
    name_scores = []
    for r in matched_res:
        if r.guest_name:
            score = name_similarity(tx.description, r.guest_name)
            name_scores.append(score)
    scores["name"] = max(name_scores) if name_scores else 0.5

    # 3. Combine LLM confidence with algorithmic validation
    llm_conf = match.details.get("llm_confidence", match.confidence_score)
    algo_conf = (scores["amount"] * 0.6 + scores["name"] * 0.4)

    # Hybrid score: weighted combination
    final_score = llm_conf * 0.6 + algo_conf * 0.4
    match.confidence_score = round(final_score, 4)
    match.confidence_tier = (
        "HIGH" if final_score >= 0.85
        else "MEDIUM" if final_score >= 0.60
        else "LOW"
    )
    match.match_type = "hybrid"
    match.details["algorithmic_scores"] = scores
    match.details["final_score_breakdown"] = {
        "llm_weight": 0.6,
        "llm_score": llm_conf,
        "algo_weight": 0.4,
        "algo_score": algo_conf,
    }

    return match
