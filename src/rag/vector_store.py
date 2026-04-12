"""RAG Vector Store using ChromaDB.

Design principles:
- Embeddings capture reconciliation PATTERNS, not absolute values
- Metadata filters allow pre-filtering by channel, country, property before vector search
- Compact token format for LLM context — CSV-like, not verbose JSON
- Commission rates, taxes, bank formats are variable per tenant — stored as metadata, not hardcoded
"""

import json
import logging
from pathlib import Path

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

CHROMA_DIR = Path(__file__).parent.parent.parent / "chroma_db"


def get_chroma_client() -> chromadb.ClientAPI:
    """Get or create persistent ChromaDB client."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(client: chromadb.ClientAPI | None = None) -> chromadb.Collection:
    """Get or create the reconciliation examples collection."""
    if client is None:
        client = get_chroma_client()
    return client.get_or_create_collection(
        name="reconciliation_examples",
        metadata={"hnsw:space": "cosine"},
    )


def _build_embedding_text(record: dict) -> str:
    """Build text for embedding that captures the reconciliation PATTERN.

    Focus on:
    - Channel type and how it appears in bank descriptions
    - Number of reservations per payout (1 vs grouped)
    - Commission pattern (rate, PSF)
    - Amount range category (not exact amount — patterns transfer better)
    - Bank description format

    This makes embeddings transferable across hotels with different
    absolute values but similar reconciliation patterns.
    """
    channel = record.get("channel", "unknown")
    bank_desc = record.get("bank_description", "")
    amount = record.get("bank_amount", 0)
    reservations = record.get("reservations", [])
    num_res = len(reservations)

    # Amount range (pattern, not absolute)
    if amount < 200:
        amount_range = "small (<200€)"
    elif amount < 1000:
        amount_range = "medium (200-1000€)"
    elif amount < 5000:
        amount_range = "large (1000-5000€)"
    else:
        amount_range = "very large (>5000€)"

    # Payout type
    if num_res == 0:
        payout_type = "single payment, no reservation details"
    elif num_res == 1:
        payout_type = "single reservation payment"
    else:
        payout_type = f"grouped payout with {num_res} reservations"

    # Commission info from reservations
    commission_info = ""
    if reservations and "commission_pct" in reservations[0]:
        pcts = set(str(r.get("commission_pct", "")) for r in reservations if r.get("commission_pct"))
        if pcts:
            commission_info = f"Commission rates: {', '.join(pcts)}."

    parts = [
        f"Channel: {channel}.",
        f"Bank description pattern: {bank_desc[:120]}.",
        f"Amount range: {amount_range}.",
        f"Payout type: {payout_type}.",
    ]
    if commission_info:
        parts.append(commission_info)
    if record.get("notes"):
        parts.append(f"Notes: {record['notes'][:100]}.")

    return " ".join(parts)


def _build_compact_context(record: dict) -> str:
    """Build compact LLM context from a record — optimized for minimal tokens.

    Uses CSV-like format instead of JSON to save ~40% tokens.
    Only includes fields the LLM needs to reason about matching.
    """
    channel = record.get("channel", "?")
    bank_amt = record.get("bank_amount", 0)
    bank_desc = record.get("bank_description", "")[:100]
    payout_ref = record.get("payout_reference", "")
    reservations = record.get("reservations", [])

    lines = [f"[EXAMPLE|{channel}|bank:{bank_amt}|ref:{payout_ref}]"]
    lines.append(f"desc: {bank_desc}")

    if reservations:
        for i, r in enumerate(reservations[:5]):  # Max 5 reservations per example
            if "reservation_id" in r:
                lines.append(
                    f"  res{i+1}: id={r.get('reservation_id','?')}"
                    f"|gross={r.get('gross_amount',0)}"
                    f"|comm={r.get('commission',0)}"
                    f"|net={r.get('net_amount',0)}"
                )
            elif "confirmation_code" in r:
                lines.append(
                    f"  res{i+1}: code={r.get('confirmation_code','?')}"
                    f"|guest={r.get('guest_name','?')}"
                    f"|net={r.get('net_amount',0)}"
                    f"|gross={r.get('gross_amount',0)}"
                )
            elif "charge_id" in r:
                lines.append(
                    f"  res{i+1}: charge={r.get('charge_id','?')[:20]}"
                    f"|amt={r.get('amount',0)}"
                    f"|fee={r.get('fee',0)}"
                )
        if len(reservations) > 5:
            lines.append(f"  ...+{len(reservations)-5} more")

    return "\n".join(lines)


def ingest_ground_truth(ground_truth_path: str | None = None):
    """Ingest ground truth records into ChromaDB."""
    if ground_truth_path is None:
        ground_truth_path = str(
            Path(__file__).parent.parent.parent / "rag_data" / "ground_truth.json"
        )

    with open(ground_truth_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    collection = get_collection()

    ids = []
    documents = []
    metadatas = []

    for i, record in enumerate(records):
        doc_id = f"gt_{record['channel']}_{i:04d}"
        embedding_text = _build_embedding_text(record)
        compact_ctx = _build_compact_context(record)

        ids.append(doc_id)
        documents.append(embedding_text)
        metadatas.append({
            "channel": record.get("channel", "unknown"),
            "bank_name": record.get("bank_name", ""),
            "bank_amount": float(record.get("bank_amount", 0)),
            "num_reservations": len(record.get("reservations", [])),
            "payout_reference": record.get("payout_reference", "") or "",
            "compact_context": compact_ctx,
            "confidence": record.get("confidence", "confirmed"),
        })

    # Upsert in batches
    batch_size = 50
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    logger.info(f"Ingested {len(ids)} records into ChromaDB")
    return len(ids)


def retrieve_similar(
    bank_description: str,
    bank_amount: float,
    channel: str | None = None,
    n_results: int = 5,
    amount_tolerance: float = 0.5,
) -> list[dict]:
    """Retrieve similar reconciliation examples for RAG context.

    Args:
        bank_description: The bank transaction description to match
        bank_amount: The bank transaction amount
        channel: Optional channel filter (pre-filter before vector search)
        n_results: Max examples to return (default 5, keep low for token optimization)
        amount_tolerance: Fraction tolerance for amount filtering (0.5 = ±50%)

    Returns:
        List of compact context strings + metadata for LLM injection
    """
    collection = get_collection()

    # Build query text focusing on the pattern
    if bank_amount < 200:
        amount_range = "small (<200€)"
    elif bank_amount < 1000:
        amount_range = "medium (200-1000€)"
    elif bank_amount < 5000:
        amount_range = "large (1000-5000€)"
    else:
        amount_range = "very large (>5000€)"

    query_text = (
        f"Channel: {channel or 'unknown'}. "
        f"Bank description pattern: {bank_description[:120]}. "
        f"Amount range: {amount_range}."
    )

    # Pre-filter by channel if known
    where_filter = None
    if channel:
        where_filter = {"channel": {"$eq": channel}}

    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=min(n_results, 10),
            where=where_filter,
            include=["metadatas", "distances"],
        )
    except Exception as e:
        logger.warning(f"ChromaDB query failed: {e}")
        return []

    examples = []
    if results and results["metadatas"]:
        for meta, distance in zip(results["metadatas"][0], results["distances"][0]):
            examples.append({
                "context": meta.get("compact_context", ""),
                "channel": meta.get("channel", ""),
                "bank_amount": meta.get("bank_amount", 0),
                "num_reservations": meta.get("num_reservations", 0),
                "similarity": round(1 - distance, 4),  # cosine distance -> similarity
            })

    return examples


def build_rag_context(
    transactions: list[dict],
    detected_channels: list[str | None],
    max_examples_per_tx: int = 3,
    max_total_tokens: int = 2000,
) -> str:
    """Build optimized RAG context for the LLM matching prompt.

    Token budget:
    - ~2000 tokens for RAG examples (configurable)
    - Each compact example is ~50-100 tokens
    - So ~20-40 examples max, but we limit to 3 per transaction

    This keeps the total prompt under 4K tokens for Haiku,
    leaving room for the transaction data and instructions.
    """
    all_examples = []
    seen_contexts = set()

    for tx, channel in zip(transactions, detected_channels):
        examples = retrieve_similar(
            bank_description=tx.get("description", ""),
            bank_amount=tx.get("amount", 0),
            channel=channel,
            n_results=max_examples_per_tx,
        )
        for ex in examples:
            ctx = ex["context"]
            if ctx and ctx not in seen_contexts:
                seen_contexts.add(ctx)
                all_examples.append(ex)

    if not all_examples:
        return "No previous reconciliation examples available."

    # Sort by similarity, take top examples within token budget
    all_examples.sort(key=lambda x: x["similarity"], reverse=True)

    lines = ["## Previous confirmed reconciliation examples:"]
    token_estimate = 10  # header
    for ex in all_examples:
        ctx = ex["context"]
        ctx_tokens = len(ctx) // 4  # rough estimate: 4 chars per token
        if token_estimate + ctx_tokens > max_total_tokens:
            break
        lines.append(ctx)
        lines.append(f"  [similarity={ex['similarity']}]")
        token_estimate += ctx_tokens + 5

    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Ingest
    count = ingest_ground_truth()
    print(f"Ingested {count} records")

    # Test retrieval
    examples = retrieve_similar(
        bank_description="Transferencia De Booking.com B.v., Concepto No.abc123/id.343496.",
        bank_amount=3500.0,
        channel="booking",
        n_results=3,
    )
    print(f"\nRetrieved {len(examples)} examples for Booking query:")
    for ex in examples:
        print(f"  similarity={ex['similarity']} channel={ex['channel']} "
              f"amount={ex['bank_amount']} reservations={ex['num_reservations']}")
        print(f"  {ex['context'][:150]}...")
