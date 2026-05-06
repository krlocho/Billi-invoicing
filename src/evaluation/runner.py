"""Run all strategies against a reconciliation and print metrics.

Usage:
    uv run python -m src.evaluation.runner <reconciliation_id>
                                            [--strategies algorithmic_only,llm_only,hybrid]
                                            [--output results.json]

By default runs `algorithmic_only` only (no API cost). Add `llm_only`
or `hybrid` to call the LLM (will hit ANTHROPIC_API_KEY / OPENAI_API_KEY
/ GOOGLE_API_KEY according to settings).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict

from src.database import SessionLocal
from src.evaluation.dataset import build_dataset
from src.evaluation.metrics import evaluate, format_table
from src.evaluation.strategies import algorithmic_only, hybrid, hybrid_from_db, llm_only
from src.matching.learned_commission import learned_rate_lookup
from src.tasks.reconciliation_tasks import _build_tenant_context

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("eval")


STRATEGIES = {
    "algorithmic_only": "no LLM — subset-sum + learned commission + fuzzy names",
    "llm_only": "LLM proposes matches, no algorithmic validator",
    "hybrid": "current production pipeline (LLM + validator) — re-runs LLM",
    "hybrid_from_db": "matches already produced by production pipeline (no API cost)",
}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("reconciliation_id")
    parser.add_argument(
        "--strategies",
        default="algorithmic_only",
        help=f"comma-separated subset of {','.join(STRATEGIES)}",
    )
    parser.add_argument("--output", default=None, help="optional path to write JSON results")
    args = parser.parse_args(argv)

    requested = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in requested if s not in STRATEGIES]
    if unknown:
        log.error(f"Unknown strategies: {unknown}. Available: {list(STRATEGIES)}")
        return 2

    db = SessionLocal()
    try:
        ds = build_dataset(db, args.reconciliation_id)
        log.info(f"Reconciliation: {ds.reconciliation_id}")
        log.info(f"  bank transactions: {len(ds.transactions)}")
        log.info(f"  reservations:      {len(ds.reservations)}")
        log.info(f"  ground truth (confirmed): {len(ds.positive_truth)}")
        log.info(f"  ground truth (rejected):  {len(ds.negative_truth)}")

        commission_lookup = learned_rate_lookup(db, ds.tenant_id)
        tenant_context = _build_tenant_context(db, ds.tenant_id, commission_lookup)
        log.info("\nLearned commissions:")
        for ch, info in commission_lookup.items():
            tag = "learned" if info.get("is_learned") else "default"
            log.info(f"  {ch}: {info['rate']*100:.2f}%  ({tag}, n={info.get('sample_size', 0)})")

        results = []
        for name in requested:
            log.info(f"\n>> running {name} — {STRATEGIES[name]}")
            if name == "algorithmic_only":
                preds = algorithmic_only(ds.transactions, ds.reservations, commission_lookup)
            elif name == "llm_only":
                preds = llm_only(ds.transactions, ds.reservations, tenant_context)
            elif name == "hybrid":
                preds = hybrid(ds.transactions, ds.reservations, tenant_context, commission_lookup)
            elif name == "hybrid_from_db":
                preds = hybrid_from_db(db, ds.reconciliation_id)
            else:
                continue
            metrics = evaluate(name, preds, ds)
            results.append(metrics)

        log.info("\n" + format_table(results))

        if args.output:
            with open(args.output, "w") as f:
                json.dump(
                    {
                        "reconciliation_id": ds.reconciliation_id,
                        "n_transactions": len(ds.transactions),
                        "n_reservations": len(ds.reservations),
                        "n_truth_confirmed": len(ds.positive_truth),
                        "results": [asdict(r) for r in results],
                    },
                    f,
                    indent=2,
                )
            log.info(f"\nWrote results to {args.output}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
