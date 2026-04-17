"""Core reconciliation engine — LLM-first with RAG augmentation.

Architecture:
- RAG retrieves similar past reconciliations from ChromaDB
- Haiku 4.5 handles routine matching (fast, cheap, ~85% of cases)
- Sonnet 4.6 escalates for ambiguous cases (confidence < 0.7)
- Algorithmic validation layer verifies LLM decisions
- Token-optimized: compact CSV format, pre-filtered RAG context

Commission rates, taxes, and bank formats are VARIABLE per tenant —
passed as context, never hardcoded in prompts.
"""

import json
import logging
from dataclasses import dataclass, field

from src.config import settings
from src.matching.commission import amount_matches, calculate_expected_net_for_group
from src.matching.fuzzy_names import name_similarity

logger = logging.getLogger(__name__)

# LLM model tiers — fast for routine, smart for ambiguous
MODELS = {
    "anthropic": {"fast": "claude-haiku-4-5-20251001", "smart": "claude-sonnet-4-6-20250514"},
    "openai": {"fast": "gpt-4o-mini", "smart": "gpt-4o-mini"},
    "google": {"fast": "gemini-2.5-flash", "smart": "gemini-2.5-pro"},
}
AMBIGUITY_THRESHOLD = 0.70  # Below this, escalate to stronger model


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
    match_type: str  # llm_haiku, llm_sonnet, hybrid
    reasoning: str
    details: dict = field(default_factory=dict)


# Compact system prompt — optimized for minimal tokens
SYSTEM_PROMPT = """You are a hotel bank reconciliation expert. Match bank transactions to channel reservations.

Rules:
1. One bank payment can cover MULTIPLE reservations (grouped payout)
2. Payment = sum(reservation_amounts) - channel_commission
3. Names may differ between bank and reservation
4. Channels pay 1-15 days after checkout

{tenant_context}

Respond ONLY with valid JSON:
{{"matches":[{{"tx_id":"...","res_ids":["..."],"confidence":0.92,"reasoning":"...","channel":"booking","commission_rate":0.22}}],"unmatched_tx":["..."],"unmatched_res":["..."]}}"""

# Compact data format — ~40% fewer tokens than JSON
DATA_TEMPLATE = """{rag_context}

## Bank transactions to reconcile:
{transactions_compact}

## Available reservations (unreconciled):
{reservations_compact}"""


def run_matching(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    feedback_examples: list[dict] | None = None,
    tenant_context: str = "",
) -> list[MatchResult]:
    """Run LLM-first matching with RAG augmentation and tiered models."""
    if not transactions or not reservations:
        return []

    # Step 1: Detect channels from bank descriptions
    detected_channels = [_detect_channel(tx.description) for tx in transactions]

    # Step 2: Retrieve RAG context (similar past reconciliations)
    rag_context = _get_rag_context(transactions, detected_channels)

    # Step 3: LLM matching with Haiku (fast/cheap)
    llm_matches = _llm_match(
        transactions, reservations, detected_channels,
        rag_context, tenant_context, model_tier="fast",
    )

    # Step 4: Algorithmic validation
    validated = []
    ambiguous_txs = []
    for match in llm_matches:
        result = _validate_match(match, transactions, reservations)
        if result.confidence_score < AMBIGUITY_THRESHOLD:
            ambiguous_txs.append(result)
        else:
            validated.append(result)

    # Step 5: Escalate ambiguous cases to Sonnet (smarter, more expensive)
    if ambiguous_txs:
        logger.info(f"Escalating {len(ambiguous_txs)} ambiguous matches to stronger model")
        ambiguous_tx_ids = {m.bank_transaction_id for m in ambiguous_txs}
        ambiguous_transactions = [t for t in transactions if t.id in ambiguous_tx_ids]
        if ambiguous_transactions:
            retry_matches = _llm_match(
                ambiguous_transactions, reservations,
                [_detect_channel(t.description) for t in ambiguous_transactions],
                rag_context, tenant_context, model_tier="smart",
            )
            for match in retry_matches:
                result = _validate_match(match, transactions, reservations)
                result.match_type = "hybrid_escalated"
                validated.append(result)

    return validated


def _detect_channel(description: str) -> str | None:
    """Detect channel from bank description."""
    desc_lower = description.lower()
    if "booking.com" in desc_lower or "booking" in desc_lower:
        return "booking"
    elif "airbnb" in desc_lower:
        return "airbnb"
    elif "stripe" in desc_lower:
        return "stripe"
    elif "travelscape" in desc_lower or "expedia" in desc_lower:
        return "expedia"
    elif "sunweb" in desc_lower:
        return "sunweb"
    return None


def _get_rag_context(
    transactions: list[TransactionData],
    detected_channels: list[str | None],
) -> str:
    """Retrieve RAG context, with graceful fallback if ChromaDB unavailable."""
    try:
        from src.rag.vector_store import build_rag_context
        tx_dicts = [{"description": t.description, "amount": t.amount} for t in transactions]
        return build_rag_context(tx_dicts, detected_channels, max_examples_per_tx=3)
    except Exception as e:
        logger.warning(f"RAG retrieval failed, proceeding without: {e}")
        return "No previous reconciliation examples available."


def _build_compact_transactions(transactions: list[TransactionData]) -> str:
    """Build compact CSV-like representation of transactions (~40% fewer tokens)."""
    lines = ["id|date|amount|description"]
    for tx in transactions:
        lines.append(f"{tx.id[:8]}|{tx.date}|{tx.amount}|{tx.description[:80]}")
    return "\n".join(lines)


def _build_compact_reservations(reservations: list[ReservationData]) -> str:
    """Build compact CSV-like representation of reservations."""
    lines = ["id|res_id|guest|checkin|checkout|gross|net|channel"]
    for r in reservations:
        lines.append(
            f"{r.id[:8]}|{r.reservation_id or '?'}|{r.guest_name or '?'}"
            f"|{r.checkin_date or '?'}|{r.checkout_date or '?'}"
            f"|{r.gross_amount or 0}|{r.net_amount or 0}|{r.channel_code or '?'}"
        )
    return "\n".join(lines)


def _llm_match(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    detected_channels: list[str | None],
    rag_context: str,
    tenant_context: str,
    model_tier: str = "fast",
) -> list[MatchResult]:
    """Call LLM for matching. Tier controls model selection."""

    system = SYSTEM_PROMPT.format(
        tenant_context=tenant_context or "No specific tenant context provided.",
    )
    user_prompt = DATA_TEMPLATE.format(
        rag_context=rag_context,
        transactions_compact=_build_compact_transactions(transactions),
        reservations_compact=_build_compact_reservations(reservations),
    )

    try:
        logger.info(f"Calling LLM ({model_tier}) with {len(transactions)} transactions and {len(reservations)} reservations")
        response_text = _call_llm(system, user_prompt, model_tier)
        logger.info(f"LLM response length: {len(response_text)} chars")
        logger.info(f"LLM response preview: {response_text[:500]}")
        matches = _parse_response(response_text)
        logger.info(f"Parsed {len(matches)} matches from LLM response")
        return matches
    except Exception as e:
        logger.error(f"LLM matching failed ({model_tier}): {e}")
        return []


def _call_llm(system: str, prompt: str, model_tier: str = "fast") -> str:
    """Call LLM with tiered model selection.

    fast  = cheap/fast model for routine matching
    smart = stronger model for ambiguous cases

    Supports: Anthropic (Claude), OpenAI (GPT), Google (Gemini)
    """
    provider = settings.default_llm_provider

    if provider == "google" and settings.google_api_key:
        from google import genai
        client = genai.Client(api_key=settings.google_api_key)
        model = MODELS["google"][model_tier]
        response = client.models.generate_content(
            model=model,
            contents=f"{system}\n\n{prompt}",
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
            ),
        )
        return response.text

    elif provider == "anthropic" and settings.anthropic_api_key:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        model = MODELS["anthropic"][model_tier]
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    elif provider == "openai" and settings.openai_api_key:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key)
        model = MODELS["openai"][model_tier]
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content

    else:
        raise RuntimeError(
            f"No API key configured for provider '{provider}'. "
            "Set GOOGLE_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY in .env"
        )


def _parse_response(response_text: str) -> list[MatchResult]:
    """Parse LLM JSON response into MatchResult objects."""
    try:
        data = json.loads(response_text)
    except json.JSONDecodeError:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                data = json.loads(response_text[start:end])
            except json.JSONDecodeError:
                return []
        else:
            return []

    matches = []
    for m in data.get("matches", []):
        confidence = float(m.get("confidence", 0))
        tier = "HIGH" if confidence >= 0.85 else "MEDIUM" if confidence >= 0.60 else "LOW"
        matches.append(MatchResult(
            bank_transaction_id=m.get("tx_id", m.get("bank_transaction_id", "")),
            reservation_ids=m.get("res_ids", m.get("reservation_ids", [])),
            confidence_score=confidence,
            confidence_tier=tier,
            amount_difference=0,
            match_type=f"llm",
            reasoning=m.get("reasoning", ""),
            details={
                "channel": m.get("channel"),
                "commission_rate": m.get("commission_rate"),
                "llm_confidence": confidence,
            },
        ))
    return matches


def _validate_match(
    match: MatchResult,
    transactions: list[TransactionData],
    reservations: list[ReservationData],
) -> MatchResult:
    """Validate LLM match with algorithmic checks."""
    tx = next((t for t in transactions if t.id == match.bank_transaction_id), None)
    if not tx:
        # Try short ID match
        tx = next((t for t in transactions if t.id[:8] == match.bank_transaction_id[:8]), None)
        if tx:
            match.bank_transaction_id = tx.id

    if not tx:
        match.confidence_score = 0
        match.confidence_tier = "LOW"
        return match

    matched_res = [r for r in reservations if r.id in match.reservation_ids or r.id[:8] in [rid[:8] for rid in match.reservation_ids]]
    if matched_res:
        # Update to full IDs
        match.reservation_ids = [r.id for r in matched_res]

    if not matched_res:
        match.confidence_score *= 0.5
        match.confidence_tier = "LOW"
        return match

    scores = {}

    # 1. Amount validation
    channel_code = match.details.get("channel") or _detect_channel(tx.description) or "booking"
    gross_amounts = [r.gross_amount or 0 for r in matched_res]
    expected_net = calculate_expected_net_for_group(gross_amounts, channel_code)
    amount_ok, amount_diff = amount_matches(abs(tx.amount), expected_net, tolerance_pct=0.05)
    match.amount_difference = round(amount_diff, 2)
    scores["amount"] = 1.0 if amount_ok else max(0, 1 - (amount_diff / max(abs(tx.amount), 1)))

    # 2. Name similarity
    name_scores = []
    for r in matched_res:
        if r.guest_name:
            score = name_similarity(tx.description, r.guest_name)
            name_scores.append(score)
    scores["name"] = max(name_scores) if name_scores else 0.5

    # 3. Hybrid score: LLM confidence (60%) + algorithmic (40%)
    llm_conf = match.details.get("llm_confidence", match.confidence_score)
    algo_conf = scores["amount"] * 0.7 + scores["name"] * 0.3
    final_score = llm_conf * 0.6 + algo_conf * 0.4

    match.confidence_score = round(final_score, 4)
    match.confidence_tier = (
        "HIGH" if final_score >= 0.85
        else "MEDIUM" if final_score >= 0.60
        else "LOW"
    )
    match.match_type = "hybrid"
    match.details["scores"] = scores

    return match
