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
import re
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
    payout_ref: str | None = None


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
5. In `res_ids`, return the internal 8-char id from the provided list — NOT the channel's reservation code.

{tenant_context}

Respond ONLY with valid JSON. The `reasoning` field must be ≤ 12 words, no math, no self-correction:
{{"matches":[{{"tx_id":"...","res_ids":["..."],"confidence":0.92,"reasoning":"<12 words>","channel":"booking","commission_rate":0.22}}],"unmatched_tx":["..."],"unmatched_res":["..."]}}"""

# Compact data format — ~40% fewer tokens than JSON
DATA_TEMPLATE = """{rag_context}
{examples_block}
## Bank transactions to reconcile:
{transactions_compact}

## Available reservations (unreconciled):
{reservations_compact}"""


def run_matching(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
    feedback_examples: list[dict] | None = None,
    tenant_context: str = "",
    commission_lookup: dict[str, dict] | None = None,
    examples_block: str = "",
) -> list[MatchResult]:
    """Run LLM-first matching with RAG augmentation and tiered models.

    `commission_lookup` maps channel_code -> {rate, sample_size, is_learned, psf_rate}
    and is used by the algorithmic validator instead of hardcoded rates.
    `examples_block` is a pre-formatted few-shot examples block injected
    into the LLM prompt — see src.matching.feedback_examples.
    """
    if not transactions or not reservations:
        return []

    commission_lookup = commission_lookup or {}

    # Step 0: Deterministic lookups by payout reference (Booking's
    # `Concepto No.XXX` ↔ Statement Descriptor). Whatever resolves here
    # is removed from the LLM workload.
    deterministic = _match_by_payout_ref(transactions, reservations)
    resolved_tx_ids = {m.bank_transaction_id for m in deterministic}
    remaining = [t for t in transactions if t.id not in resolved_tx_ids]
    if deterministic:
        logger.info(
            f"Deterministic payout_ref matched {len(deterministic)} "
            f"bank transactions before LLM stage"
        )
    if not remaining:
        return deterministic

    # Step 1: Detect channels from bank descriptions
    detected_channels = [_detect_channel(tx.description) for tx in remaining]

    # Step 2: Retrieve RAG context (similar past reconciliations)
    rag_context = _get_rag_context(remaining, detected_channels)

    # Step 3: LLM matching with Haiku (fast/cheap)
    llm_matches = _llm_match(
        remaining, reservations, detected_channels,
        rag_context, tenant_context, model_tier="fast",
        examples_block=examples_block,
    )

    # Step 4: Algorithmic validation
    validated = []
    ambiguous_txs = []
    for match in llm_matches:
        result = _validate_match(match, transactions, reservations, commission_lookup)
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
                examples_block=examples_block,
            )
            for match in retry_matches:
                result = _validate_match(match, transactions, reservations, commission_lookup)
                result.match_type = "hybrid_escalated"
                validated.append(result)

    return deterministic + validated


# Bank "Concepto No.<ref>" identifier — captures the 16-char payout
# reference (always lowercased by Spanish bank statements). The optional
# `/id.<property>` suffix is informational and we don't depend on it.
_CONCEPTO_RE = re.compile(r"concepto\s+no\.?\s*([a-z0-9]{8,})", re.IGNORECASE)


def _extract_payout_ref(description: str) -> str | None:
    """Pull the payout reference out of a bank statement line."""
    if not description:
        return None
    m = _CONCEPTO_RE.search(description)
    return m.group(1).lower() if m else None


def _match_by_payout_ref(
    transactions: list[TransactionData],
    reservations: list[ReservationData],
) -> list[MatchResult]:
    """Deterministic match using channel-provided payout linkage.

    Two paths, depending on whether the bank exposes the payout reference
    in its description (Booking does, Airbnb / Stripe / Expedia do not):

      A. Reference present in bank text (Booking): regex out
         `Concepto No.<ref>` → reservations with same `payout_ref` →
         emit match. O(1) lookup, zero ambiguity.

      B. Reference absent in bank text but stable on the channel side
         (Airbnb): group reservations by their `payout_ref` to recover
         the original payout. For each Airbnb bank line, find the group
         whose net-sum equals the bank amount within tolerance and whose
         dates are within a ±7-day window of the bank date. If exactly
         one group satisfies both constraints, the match is unambiguous.

    Booking pre-November rows in the DB don't yet carry payout_ref →
    they silently fall through to the LLM stage. Same for Stripe groups
    once we wire up that side.
    """
    out: list[MatchResult] = []
    used_reservation_ids: set[str] = set()

    # Path A — bank carries the ref
    by_ref: dict[str, list[ReservationData]] = {}
    for r in reservations:
        if r.payout_ref:
            by_ref.setdefault(r.payout_ref.lower(), []).append(r)

    for tx in transactions:
        ref = _extract_payout_ref(tx.description)
        if not ref:
            continue
        group = by_ref.get(ref)
        if not group:
            continue
        net_sum = sum((r.net_amount or 0) for r in group)
        amount = abs(tx.amount)
        amount_diff = round(amount - net_sum, 2)
        out.append(MatchResult(
            bank_transaction_id=tx.id,
            reservation_ids=[r.id for r in group],
            confidence_score=1.0,
            confidence_tier="HIGH",
            amount_difference=amount_diff,
            match_type="deterministic_payout_ref",
            reasoning=f"Bank Concepto No.{ref} matches payout containing {len(group)} reservations",
            details={
                "payout_ref": ref,
                "channel": "booking",
                "net_sum": round(net_sum, 2),
                "bank_amount": amount,
                "amount_diff": amount_diff,
            },
        ))
        for r in group:
            used_reservation_ids.add(r.id)

    matched_tx_ids = {m.bank_transaction_id for m in out}

    # Path B — bank text is identical for every transfer, but the
    # channel-side payout grouping is structural. We rebuild the implicit
    # "payout summary" by grouping reservations by their payout_ref and
    # matching `sum(net) ≈ bank_amount` within a date window.
    from datetime import date as _date, datetime as _dt, timedelta

    def _parse(s):
        if not s:
            return None
        if isinstance(s, _date):
            return s
        try:
            return _dt.strptime(str(s)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    AMOUNT_TOL = 0.05  # EUR
    DATE_WINDOW = timedelta(days=7)

    # Build per-channel groups keyed by payout_ref. Filter out groups
    # whose reservations are already used by Path A.
    channel_groups: dict[str, dict[str, list[ReservationData]]] = {}
    for r in reservations:
        if not r.payout_ref or r.id in used_reservation_ids:
            continue
        ch = (r.channel_code or "").lower() or "unknown"
        if ch == "booking":
            continue  # Booking is handled exclusively by Path A
        channel_groups.setdefault(ch, {}).setdefault(r.payout_ref, []).append(r)

    for tx in transactions:
        if tx.id in matched_tx_ids:
            continue
        ch = (_detect_channel(tx.description) or "").lower()
        if not ch:
            continue
        ch_buckets = channel_groups.get(ch)
        if not ch_buckets:
            continue
        amount = abs(tx.amount)
        tx_date = _parse(tx.date)
        candidates: list[tuple[str, list[ReservationData], float]] = []
        for ref, group in ch_buckets.items():
            net_sum = sum((r.net_amount or 0) for r in group)
            if abs(net_sum - amount) > AMOUNT_TOL:
                continue
            # Date sanity: at least one reservation's checkout/checkin
            # within ±7 days of the bank date (the bank receives 0-3
            # days after Airbnb's payout date).
            if tx_date:
                dates = [
                    _parse(r.checkout_date) or _parse(r.checkin_date)
                    for r in group
                ]
                dates = [d for d in dates if d]
                if not dates:
                    continue
                if not any(abs(tx_date - d) <= DATE_WINDOW for d in dates):
                    continue
            candidates.append((ref, group, net_sum))

        if len(candidates) != 1:
            # 0 → no structural match (let LLM try)
            # >1 → ambiguous (also defer to LLM — rare but possible)
            continue
        ref, group, net_sum = candidates[0]
        # Skip if any reservation in this group has already been used by Path A.
        if any(r.id in used_reservation_ids for r in group):
            continue
        out.append(MatchResult(
            bank_transaction_id=tx.id,
            reservation_ids=[r.id for r in group],
            confidence_score=1.0,
            confidence_tier="HIGH",
            amount_difference=round(amount - net_sum, 2),
            match_type="deterministic_amount_date",
            reasoning=f"{ch} payout {ref} sum={net_sum:.2f} matches bank {amount:.2f}",
            details={
                "payout_ref": ref,
                "channel": ch,
                "net_sum": round(net_sum, 2),
                "bank_amount": amount,
                "group_size": len(group),
            },
        ))
        for r in group:
            used_reservation_ids.add(r.id)
    return out


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
    examples_block: str = "",
) -> list[MatchResult]:
    """Call LLM for matching. Tier controls model selection."""

    system = SYSTEM_PROMPT.format(
        tenant_context=tenant_context or "No specific tenant context provided.",
    )
    user_prompt = DATA_TEMPLATE.format(
        rag_context=rag_context,
        examples_block=examples_block or "",
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
                max_output_tokens=32768,
                temperature=0.0,
                # Gemini 2.5 Flash burns output tokens on chain-of-thought
                # inside the `reasoning` field if we let it. Cap thinking.
                thinking_config=genai.types.ThinkingConfig(thinking_budget=0),
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
    """Parse LLM JSON response into MatchResult objects.

    The response is occasionally truncated (LLM hits its output token cap
    mid-array). We recover by extracting whatever complete `{...}` match
    objects exist before the truncation point.
    """
    def _try_load(s: str) -> dict | None:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    data = _try_load(response_text)
    if data is None:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start >= 0 and end > start:
            data = _try_load(response_text[start:end])
    if data is None:
        # Tolerant recovery: pull individual match objects from the buffer
        # by scanning for balanced `{...}` blocks that contain "tx_id".
        recovered: list[dict] = []
        i = response_text.find('"matches"')
        if i < 0:
            return []
        i = response_text.find("[", i)
        if i < 0:
            return []
        depth = 0
        start_obj = -1
        in_str = False
        esc = False
        for j in range(i + 1, len(response_text)):
            c = response_text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
                continue
            if c == "{":
                if depth == 0:
                    start_obj = j
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0 and start_obj >= 0:
                    obj = _try_load(response_text[start_obj : j + 1])
                    if isinstance(obj, dict):
                        recovered.append(obj)
                    start_obj = -1
            elif c == "]" and depth == 0:
                break
        if not recovered:
            return []
        data = {"matches": recovered}

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
    commission_lookup: dict[str, dict] | None = None,
) -> MatchResult:
    """Validate LLM match with algorithmic checks."""
    commission_lookup = commission_lookup or {}
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

    # 1. Amount validation — prefer learned commission for this channel
    channel_code = match.details.get("channel") or _detect_channel(tx.description) or "booking"
    learned = commission_lookup.get(channel_code.lower())
    tenant_config = (
        {"learned_rate": learned["rate"], "psf_rate": learned.get("psf_rate", 0)}
        if learned
        else None
    )
    if learned:
        match.details["learned_commission_rate"] = learned["rate"]
        match.details["learned_commission_samples"] = learned.get("sample_size", 0)
    gross_amounts = [r.gross_amount or 0 for r in matched_res]
    expected_net = calculate_expected_net_for_group(gross_amounts, channel_code, tenant_config)
    amount_ok, amount_diff = amount_matches(abs(tx.amount), expected_net, tolerance_pct=0.05)
    match.amount_difference = round(amount_diff, 2)
    scores["amount"] = 1.0 if amount_ok else max(0, 1 - (amount_diff / max(abs(tx.amount), 1)))

    # 2. Name similarity — applies only when the bank text could plausibly
    # carry an individual guest name. Channel payouts (Booking, Airbnb,
    # Stripe, Expedia) put the *channel's* corporate name in the bank
    # description, not the guest's — comparing those is noise that drags
    # genuine matches down. Same for grouped payouts (one bank line
    # covers many guests).
    detected_for_name = _detect_channel(tx.description)
    is_channel_payout = detected_for_name is not None
    is_grouped = len(matched_res) > 1
    name_scores: list[float] = []
    if not is_channel_payout and not is_grouped:
        for r in matched_res:
            if r.guest_name:
                name_scores.append(name_similarity(tx.description, r.guest_name))
    has_names = bool(name_scores)
    scores["name"] = max(name_scores) if name_scores else None

    # 3. Date coherence — channels typically pay 0-15 days after checkout.
    # Best (closest) reservation in the group sets the score.
    def _parse_d(s):
        if not s:
            return None
        try:
            from datetime import date as _d
            if isinstance(s, _d):
                return s
            from datetime import datetime as _dt
            return _dt.strptime(str(s)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None

    tx_d = _parse_d(tx.date)
    date_deltas: list[int] = []
    for r in matched_res:
        co = _parse_d(r.checkout_date) or _parse_d(r.checkin_date)
        if tx_d and co:
            date_deltas.append((tx_d - co).days)
    if date_deltas:
        # Best (smallest non-negative) gap in the group decides.
        best = min((d for d in date_deltas if d >= 0), default=min(date_deltas))
        if 0 <= best <= 15:
            scores["date"] = 1.0
        elif 0 <= best <= 30:
            scores["date"] = 0.7
        elif -3 <= best < 0:  # tx posted same week as checkout
            scores["date"] = 0.5
        else:
            scores["date"] = max(0.0, 1.0 - abs(best) / 60.0)
        has_dates = True
    else:
        scores["date"] = None
        has_dates = False

    # 4. Channel coherence — every reservation must belong to the same
    # channel the bank description indicates.
    detected = _detect_channel(tx.description)
    if detected and matched_res:
        ch_codes = [(r.channel_code or "").lower() for r in matched_res]
        if all(c == detected for c in ch_codes):
            scores["channel"] = 1.0
        elif any(c == detected for c in ch_codes):
            scores["channel"] = 0.5
        else:
            scores["channel"] = 0.0
        has_channel = True
    else:
        scores["channel"] = None
        has_channel = False

    # 5. Hybrid score — combine whichever components are available.
    # When the name signal is missing (Booking GDPR-stripped payouts), the
    # validator falls back to amount + date + channel rather than the old
    # `name=0.5` default that artificially drove HIGH matches to MEDIUM.
    llm_conf = match.details.get("llm_confidence", match.confidence_score)
    components: list[tuple[float, float]] = []  # (value, weight)
    components.append((scores["amount"], 0.5))
    if has_names:
        components.append((scores["name"], 0.2))
    if has_dates:
        components.append((scores["date"], 0.2 if has_names else 0.3))
    if has_channel:
        components.append((scores["channel"], 0.1 if has_names else 0.2))
    total_w = sum(w for _, w in components)
    algo_conf = sum(v * w for v, w in components) / total_w if total_w else 0.0

    # Strong-LLM passthrough: high confidence + amount within tolerance
    # → keep the LLM's score (no dilution).
    if llm_conf >= 0.85 and amount_ok:
        final_score = llm_conf
    else:
        final_score = llm_conf * 0.6 + algo_conf * 0.4

    match.confidence_score = round(final_score, 4)
    match.confidence_tier = (
        "HIGH" if final_score >= 0.85
        else "MEDIUM" if final_score >= 0.60
        else "LOW"
    )
    match.match_type = "hybrid"
    match.details["scores"] = {
        **scores,
        "amount_ok": amount_ok,
        "has_names": has_names,
        "has_dates": has_dates,
        "has_channel": has_channel,
    }

    return match
