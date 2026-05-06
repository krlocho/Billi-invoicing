"""Match-level precision / recall / F1 + MRR.

A predicted match is "correct" if there exists a confirmed ground-truth
match with the same bank_transaction_id and the same set of
reservation_ids. We compare exact set equality (the system either
groups the right reservations together or it doesn't).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.evaluation.dataset import EvaluationDataset, GroundTruthMatch
from src.evaluation.strategies import MatchPrediction


@dataclass
class StrategyMetrics:
    strategy: str
    predictions: int
    confirmed_truth: int
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float
    mrr: float


def _truth_index(truth: list[GroundTruthMatch]) -> dict[str, list[GroundTruthMatch]]:
    out: dict[str, list[GroundTruthMatch]] = {}
    for t in truth:
        out.setdefault(t.bank_transaction_id, []).append(t)
    return out


def evaluate(
    strategy_name: str,
    predictions: list[MatchPrediction],
    dataset: EvaluationDataset,
) -> StrategyMetrics:
    truth_pos = dataset.positive_truth
    truth_pos_keys = {(t.bank_transaction_id, t.reservation_ids) for t in truth_pos}
    truth_by_tx = _truth_index(truth_pos)

    seen_tx: set[str] = set()
    tp = 0
    fp = 0

    # MRR: for each positive-truth bank tx, find the rank of the correct match
    # among predictions sorted by score (desc) for that tx.
    preds_by_tx: dict[str, list[MatchPrediction]] = {}
    for p in predictions:
        preds_by_tx.setdefault(p.bank_transaction_id, []).append(p)
    for lst in preds_by_tx.values():
        lst.sort(key=lambda p: -p.score)

    rr_total = 0.0
    rr_count = 0
    for t in truth_pos:
        rr_count += 1
        candidates = preds_by_tx.get(t.bank_transaction_id, [])
        rank = 0
        for i, p in enumerate(candidates, start=1):
            if p.reservation_ids == t.reservation_ids:
                rank = i
                break
        rr_total += (1.0 / rank) if rank else 0.0

    for p in predictions:
        seen_tx.add(p.bank_transaction_id)
        if (p.bank_transaction_id, p.reservation_ids) in truth_pos_keys:
            tp += 1
        else:
            # Only count as false positive if there's an alternative (correct)
            # truth match for that tx — otherwise the prediction is just on
            # a tx that isn't supposed to match anything in our truth set.
            if p.bank_transaction_id in truth_by_tx:
                fp += 1

    fn = max(0, len(truth_pos) - tp)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / len(truth_pos) if truth_pos else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    mrr = rr_total / rr_count if rr_count else 0.0

    return StrategyMetrics(
        strategy=strategy_name,
        predictions=len(predictions),
        confirmed_truth=len(truth_pos),
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
        mrr=round(mrr, 4),
    )


def format_table(rows: list[StrategyMetrics]) -> str:
    header = f"{'Strategy':<20} {'Pred':>5} {'TP':>4} {'FP':>4} {'FN':>4} {'Prec':>8} {'Rec':>8} {'F1':>8} {'MRR':>8}"
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.strategy:<20} {r.predictions:>5} {r.true_positives:>4} "
            f"{r.false_positives:>4} {r.false_negatives:>4} "
            f"{r.precision:>8.3f} {r.recall:>8.3f} {r.f1:>8.3f} {r.mrr:>8.3f}"
        )
    return "\n".join(lines)
