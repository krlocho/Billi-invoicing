"""K-fold cross-validation for few-shot evaluation.

The basic eval feeds 8 confirmed labels back to the LLM AND evaluates
against the same 31-label set → trivial leakage. This module splits the
labelled bank transactions into K disjoint folds and, per fold:

  • builds the few-shot block from the *other* folds' labels only,
  • runs the strategy with that block,
  • scores predictions on the held-out fold (and the no-match labels for
    its bank txs, used as true negatives in precision).

Final metrics are micro-averaged over folds (sum TP/FP/FN across folds,
then compute precision / recall / F1).
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.evaluation.dataset import EvaluationDataset, GroundTruthMatch
from src.evaluation.metrics import StrategyMetrics
from src.evaluation.strategies import MatchPrediction, hybrid, llm_only
from src.matching.feedback_examples import build_examples_block

logger = logging.getLogger(__name__)


@dataclass
class CVFold:
    test_tx_ids: set[str]      # bank tx ids held out for scoring
    train_tx_ids: set[str]     # all other labelled bank tx ids


def make_folds(label_tx_ids: list[str], k: int, seed: int = 42) -> list[CVFold]:
    """Split labelled tx ids into k disjoint folds (stable for a seed)."""
    rng = random.Random(seed)
    ids = list(label_tx_ids)
    rng.shuffle(ids)
    folds: list[list[str]] = [[] for _ in range(k)]
    for i, tx in enumerate(ids):
        folds[i % k].append(tx)
    out: list[CVFold] = []
    for i in range(k):
        test = set(folds[i])
        train = set(ids) - test
        out.append(CVFold(test_tx_ids=test, train_tx_ids=train))
    return out


def _scored_subset(
    predictions: list[MatchPrediction],
    truth_pos: list[GroundTruthMatch],
    test_tx_ids: set[str],
) -> tuple[int, int, int]:
    """Score only on (predictions, truth) restricted to held-out txs."""
    truth_keys = {
        (t.bank_transaction_id, t.reservation_ids)
        for t in truth_pos
        if t.bank_transaction_id in test_tx_ids
    }
    truth_by_tx = {t.bank_transaction_id for t in truth_pos if t.bank_transaction_id in test_tx_ids}
    tp = fp = 0
    for p in predictions:
        if p.bank_transaction_id not in test_tx_ids:
            continue  # not in this fold's test set
        if (p.bank_transaction_id, p.reservation_ids) in truth_keys:
            tp += 1
        elif p.bank_transaction_id in truth_by_tx:
            fp += 1
    fn = max(0, len(truth_keys) - tp)
    return tp, fp, fn


def run_cv(
    strategy_name: str,
    dataset: EvaluationDataset,
    db: Session,
    tenant_context: str,
    commission_lookup: dict,
    k_folds: int = 5,
    few_shot_k: int = 8,
    seed: int = 42,
) -> StrategyMetrics:
    """Run k-fold CV for `llm_only` or `hybrid`. Returns micro-averaged metrics."""
    label_tx_ids = [t.bank_transaction_id for t in dataset.positive_truth]
    if len(label_tx_ids) < k_folds:
        raise ValueError(f"need ≥ {k_folds} labels for {k_folds}-fold CV, got {len(label_tx_ids)}")

    folds = make_folds(label_tx_ids, k_folds, seed=seed)
    total_tp = total_fp = total_fn = 0
    total_pred = 0
    rr_sum = 0.0
    rr_count = 0

    for i, fold in enumerate(folds, start=1):
        # Exclude held-out tx ids from the few-shot pool.
        # The DB column is UUID; cast accordingly.
        exclude = {uuid.UUID(tx) for tx in fold.test_tx_ids}
        examples = build_examples_block(db, dataset.tenant_id, k=few_shot_k, exclude_tx_ids=exclude)
        examples_count = examples.count("\n- ") if examples else 0
        logger.info(
            f"  fold {i}/{k_folds}: test={len(fold.test_tx_ids)} train={len(fold.train_tx_ids)} examples={examples_count}"
        )

        if strategy_name == "llm_only":
            preds = llm_only(
                dataset.transactions, dataset.reservations,
                tenant_context=tenant_context,
                examples_block=examples,
            )
        elif strategy_name == "hybrid":
            preds = hybrid(
                dataset.transactions, dataset.reservations,
                tenant_context=tenant_context,
                commission_lookup=commission_lookup,
                examples_block=examples,
            )
        else:
            raise ValueError(f"CV only supports llm_only / hybrid, got: {strategy_name}")

        tp, fp, fn = _scored_subset(preds, dataset.positive_truth, fold.test_tx_ids)
        total_tp += tp
        total_fp += fp
        total_fn += fn
        # Count predictions for held-out txs only
        total_pred += sum(1 for p in preds if p.bank_transaction_id in fold.test_tx_ids)

        # MRR over the held-out positive truth
        preds_by_tx: dict[str, list[MatchPrediction]] = {}
        for p in preds:
            if p.bank_transaction_id in fold.test_tx_ids:
                preds_by_tx.setdefault(p.bank_transaction_id, []).append(p)
        for lst in preds_by_tx.values():
            lst.sort(key=lambda p: -p.score)
        for t in dataset.positive_truth:
            if t.bank_transaction_id not in fold.test_tx_ids:
                continue
            rr_count += 1
            cands = preds_by_tx.get(t.bank_transaction_id, [])
            rank = 0
            for j, p in enumerate(cands, start=1):
                if p.reservation_ids == t.reservation_ids:
                    rank = j
                    break
            rr_sum += (1.0 / rank) if rank else 0.0

    precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    mrr = rr_sum / rr_count if rr_count else 0.0

    return StrategyMetrics(
        strategy=f"{strategy_name}_cv{k_folds}",
        predictions=total_pred,
        confirmed_truth=len(dataset.positive_truth),
        true_positives=total_tp,
        false_positives=total_fp,
        false_negatives=total_fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        mrr=round(mrr, 4),
    )
