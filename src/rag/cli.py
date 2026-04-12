"""CLI for RAG operations — build ground truth, ingest, test retrieval."""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def cmd_build(args):
    """Build ground truth from raw data."""
    from src.rag.ground_truth import export_ground_truth_json
    path = export_ground_truth_json(args.output)
    print(f"Ground truth exported to: {path}")


def cmd_ingest(args):
    """Ingest ground truth into ChromaDB."""
    from src.rag.vector_store import ingest_ground_truth
    count = ingest_ground_truth(args.input)
    print(f"Ingested {count} records into ChromaDB")


def cmd_query(args):
    """Test RAG retrieval."""
    from src.rag.vector_store import retrieve_similar
    examples = retrieve_similar(
        bank_description=args.description,
        bank_amount=args.amount,
        channel=args.channel,
        n_results=args.n,
    )
    print(f"Retrieved {len(examples)} examples:")
    for i, ex in enumerate(examples):
        print(f"\n--- Example {i+1} (similarity={ex['similarity']}) ---")
        print(ex["context"])


def cmd_stats(args):
    """Show RAG collection stats."""
    from src.rag.vector_store import get_collection
    col = get_collection()
    print(f"Collection: {col.name}")
    print(f"Total records: {col.count()}")

    # Channel distribution
    results = col.get(include=["metadatas"])
    channels = {}
    for meta in results["metadatas"]:
        ch = meta.get("channel", "unknown")
        channels[ch] = channels.get(ch, 0) + 1
    print(f"By channel: {channels}")


def main():
    parser = argparse.ArgumentParser(description="Billi RAG CLI")
    sub = parser.add_subparsers(dest="command")

    p_build = sub.add_parser("build", help="Build ground truth JSON")
    p_build.add_argument("--output", "-o", help="Output path")

    p_ingest = sub.add_parser("ingest", help="Ingest into ChromaDB")
    p_ingest.add_argument("--input", "-i", help="Ground truth JSON path")

    p_query = sub.add_parser("query", help="Test retrieval")
    p_query.add_argument("--description", "-d", required=True)
    p_query.add_argument("--amount", "-a", type=float, required=True)
    p_query.add_argument("--channel", "-c", default=None)
    p_query.add_argument("--n", type=int, default=3)

    p_stats = sub.add_parser("stats", help="Show collection stats")

    args = parser.parse_args()
    if args.command == "build":
        cmd_build(args)
    elif args.command == "ingest":
        cmd_ingest(args)
    elif args.command == "query":
        cmd_query(args)
    elif args.command == "stats":
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
