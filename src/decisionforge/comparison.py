from dataclasses import dataclass

from .evaluator import evaluate
from .hashing import canonical_hash
from .models import (
    AlternativeComparison,
    DecisionCreate,
    RankedAlternative,
    RecomputedEvaluationSnapshot,
)


@dataclass(frozen=True)
class Recomputed:
    snapshot: RecomputedEvaluationSnapshot
    ranking_by_key: dict[str, RankedAlternative]


def _winner_margin(ranking: list[RankedAlternative], status: str) -> float | None:
    if status != "RECOMMENDED":
        return None
    eligible = sorted(
        (item for item in ranking if item.eligible),
        key=lambda item: (item.rank if item.rank is not None else 10**9, item.alternative_key),
    )
    if len(eligible) < 2:
        return None
    return round(eligible[0].score - eligible[1].score, 6)


def recompute(
    *,
    evaluation_id: str,
    decision_id: str,
    evaluation_method: str,
    decision_hash: str,
    specification: DecisionCreate,
) -> Recomputed:
    status, recommendation, ranking, _explanations, result_hash = evaluate(specification)
    recomputed_outcome_hash = canonical_hash(
        {"decision_hash": decision_hash, "result_hash": result_hash}
    )
    snapshot = RecomputedEvaluationSnapshot(
        evaluation_id=evaluation_id,
        decision_id=decision_id,
        evaluation_method=evaluation_method,
        status=status,
        recommended_alternative_key=recommendation,
        ranking=ranking,
        winner_margin=_winner_margin(ranking, status),
        decision_hash=decision_hash,
        recomputed_outcome_hash=recomputed_outcome_hash,
    )
    return Recomputed(snapshot=snapshot, ranking_by_key={item.alternative_key: item for item in ranking})


def compatibility_reasons(
    baseline_specification: DecisionCreate,
    candidate_specification: DecisionCreate,
    baseline_method: str,
    candidate_method: str,
) -> list[str]:
    reasons: list[str] = []
    if baseline_method != candidate_method:
        reasons.append(
            f"Méthodes d'évaluation incompatibles : {baseline_method} contre {candidate_method}."
        )
    baseline_alternatives = {item.key for item in baseline_specification.alternatives}
    candidate_alternatives = {item.key for item in candidate_specification.alternatives}
    if baseline_alternatives != candidate_alternatives:
        reasons.append(
            "Ensembles d'alternatives incompatibles : "
            f"baseline={sorted(baseline_alternatives)}, candidate={sorted(candidate_alternatives)}."
        )

    def criterion_contract(specification: DecisionCreate) -> dict[str, tuple[bool, float, float | None]]:
        return {
            item.key: (item.required, item.minimum_confidence, item.blocking_minimum)
            for item in specification.criteria
        }

    baseline_criteria = criterion_contract(baseline_specification)
    candidate_criteria = criterion_contract(candidate_specification)
    if baseline_criteria != candidate_criteria:
        reasons.append(
            "Contrats de critères incompatibles (clé, caractère requis, confiance minimale ou seuil bloquant)."
        )
    return reasons


def compare_recomputed(
    baseline: Recomputed,
    candidate: Recomputed,
    compatibility: list[str],
) -> tuple[
    str,
    bool,
    bool,
    bool,
    float | None,
    list[AlternativeComparison],
    list[str],
]:
    baseline_snapshot = baseline.snapshot
    candidate_snapshot = candidate.snapshot
    recommendation_changed = (
        baseline_snapshot.recommended_alternative_key
        != candidate_snapshot.recommended_alternative_key
    )
    status_changed = baseline_snapshot.status != candidate_snapshot.status
    baseline_order = [(item.alternative_key, item.rank) for item in baseline_snapshot.ranking]
    candidate_order = [(item.alternative_key, item.rank) for item in candidate_snapshot.ranking]
    ranking_changed = baseline_order != candidate_order

    margin_change = None
    if baseline_snapshot.winner_margin is not None and candidate_snapshot.winner_margin is not None:
        margin_change = round(
            candidate_snapshot.winner_margin - baseline_snapshot.winner_margin, 6
        )

    alternatives: list[AlternativeComparison] = []
    if not compatibility:
        for key in sorted(baseline.ranking_by_key):
            baseline_item = baseline.ranking_by_key[key]
            candidate_item = candidate.ranking_by_key[key]
            rank_change = None
            if baseline_item.rank is not None and candidate_item.rank is not None:
                rank_change = baseline_item.rank - candidate_item.rank
            alternatives.append(
                AlternativeComparison(
                    alternative_key=key,
                    baseline_rank=baseline_item.rank,
                    candidate_rank=candidate_item.rank,
                    rank_change=rank_change,
                    baseline_score=baseline_item.score,
                    candidate_score=candidate_item.score,
                    score_change=round(candidate_item.score - baseline_item.score, 6),
                    baseline_coverage=baseline_item.coverage,
                    candidate_coverage=candidate_item.coverage,
                    coverage_change=round(candidate_item.coverage - baseline_item.coverage, 6),
                    eligibility_changed=baseline_item.eligible != candidate_item.eligible,
                )
            )

    explanations = list(compatibility)
    if compatibility:
        qualification = "INCOMPATIBLE"
        explanations.append("Aucune conclusion d'évolution n'est tirée de snapshots incompatibles.")
    elif (
        baseline_snapshot.status == "INSUFFICIENT"
        or candidate_snapshot.status == "INSUFFICIENT"
    ):
        qualification = "INSUFFICIENT"
        explanations.append(
            "Au moins une évaluation recalculée est insuffisante ; la comparaison reste non concluante."
        )
    elif recommendation_changed or status_changed or ranking_changed:
        qualification = "CHANGED"
        if recommendation_changed:
            explanations.append(
                "La recommandation recalculée change de "
                f"{baseline_snapshot.recommended_alternative_key} à "
                f"{candidate_snapshot.recommended_alternative_key}."
            )
        if status_changed:
            explanations.append(
                f"Le statut recalculé change de {baseline_snapshot.status} à {candidate_snapshot.status}."
            )
        if ranking_changed:
            explanations.append("L'ordre ou les rangs recalculés des alternatives ont changé.")
    else:
        qualification = "CONSISTENT"
        explanations.append(
            "Le statut, la recommandation et les rangs recalculés restent cohérents."
        )

    if not compatibility:
        changed_scores = [
            item.alternative_key
            for item in alternatives
            if abs(item.score_change) > 0.000001
        ]
        changed_coverages = [
            item.alternative_key
            for item in alternatives
            if abs(item.coverage_change) > 0.000001
        ]
        if changed_scores:
            explanations.append("Scores recalculés modifiés pour : " + ", ".join(changed_scores) + ".")
        if changed_coverages:
            explanations.append(
                "Couvertures recalculées modifiées pour : " + ", ".join(changed_coverages) + "."
            )
        if margin_change is not None and abs(margin_change) > 0.000001:
            explanations.append(f"La marge du gagnant varie de {margin_change:+g} point(s).")

    return (
        qualification,
        recommendation_changed,
        status_changed,
        ranking_changed,
        margin_change,
        alternatives,
        explanations,
    )
