from decimal import Decimal, ROUND_HALF_UP

from .comparison import Recomputed
from .consensus import consensus_compatibility_reasons
from .models import (
    DecisionCreate,
    DecisionStabilityPoint,
    DecisionStabilityTransition,
)


SIX_PLACES = Decimal("0.000001")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def stability_compatibility_reasons(
    specifications: list[DecisionCreate], evaluation_methods: list[str]
) -> list[str]:
    """Use the strict logical-decision, alternatives and criteria contract."""
    return consensus_compatibility_reasons(specifications, evaluation_methods)


def _longest_streak(values: list[object]) -> int:
    longest = current = 0
    previous = object()
    for value in values:
        if value == previous:
            current += 1
        else:
            previous = value
            current = 1
        longest = max(longest, current)
    return longest


def calculate_decision_stability(
    ordered: list[tuple[Recomputed, str]], compatibility: list[str]
) -> tuple[
    str,
    list[DecisionStabilityPoint],
    list[DecisionStabilityTransition],
    int,
    int,
    int,
    float,
    int,
    int,
    int,
    str | None,
    str | None,
    float,
    float | None,
    list[str],
]:
    points: list[DecisionStabilityPoint] = []
    for index, (item, evaluated_at) in enumerate(ordered, start=1):
        snapshot = item.snapshot
        points.append(
            DecisionStabilityPoint(
                sequence=index,
                evaluation_id=snapshot.evaluation_id,
                decision_id=snapshot.decision_id,
                evaluated_at=evaluated_at,
                status=snapshot.status,
                recommended_alternative_key=snapshot.recommended_alternative_key,
                ranks={entry.alternative_key: entry.rank for entry in snapshot.ranking},
                minimum_coverage=min(entry.coverage for entry in snapshot.ranking),
                winner_margin=snapshot.winner_margin,
                decision_hash=snapshot.decision_hash,
                recomputed_outcome_hash=snapshot.recomputed_outcome_hash,
            )
        )

    transitions: list[DecisionStabilityTransition] = []
    for index, (before, after) in enumerate(zip(points, points[1:]), start=1):
        moved = sorted(
            key for key in before.ranks if before.ranks[key] != after.ranks.get(key)
        )
        transitions.append(
            DecisionStabilityTransition(
                sequence=index,
                from_evaluation_id=before.evaluation_id,
                to_evaluation_id=after.evaluation_id,
                status_changed=before.status != after.status,
                recommendation_changed=(
                    before.recommended_alternative_key != after.recommended_alternative_key
                ),
                ranking_changed=bool(moved),
                moved_alternatives=moved,
            )
        )

    status_changes = sum(item.status_changed for item in transitions)
    recommendation_changes = sum(item.recommendation_changed for item in transitions)
    ranking_changes = sum(item.ranking_changed for item in transitions)
    changed_transitions = sum(
        item.status_changed or item.recommendation_changed or item.ranking_changed
        for item in transitions
    )
    churn_rate = _rounded(Decimal(changed_transitions) / Decimal(len(transitions)))
    longest_status = _longest_streak([item.status for item in points])
    longest_recommendation = _longest_streak(
        [item.recommended_alternative_key for item in points]
    )
    stable_runs: list[int] = []
    current = 1
    for transition in transitions:
        if not (
            transition.status_changed
            or transition.recommendation_changed
            or transition.ranking_changed
        ):
            current += 1
        else:
            stable_runs.append(current)
            current = 1
    stable_runs.append(current)
    longest_unchanged = max(stable_runs)
    first_recommendation = points[0].recommended_alternative_key
    last_recommendation = points[-1].recommended_alternative_key
    worst_coverage = min(item.minimum_coverage for item in points)
    margins = [item.winner_margin for item in points if item.winner_margin is not None]
    # A missing winning margin is not silently discarded: the chronological worst case is unknown.
    worst_margin = min(margins) if len(margins) == len(points) else None

    explanations = list(compatibility)
    if compatibility:
        qualification = "INCOMPATIBLE"
        explanations.append("Aucune conclusion temporelle n'est tirée d'évaluations incompatibles.")
    elif any(item.status == "INSUFFICIENT" for item in points):
        qualification = "INSUFFICIENT"
        explanations.append(
            "Au moins une évaluation recalculée est non concluante faute de preuves suffisantes."
        )
    elif status_changes or recommendation_changes:
        qualification = "DRIFTING"
        explanations.append(
            "Au moins un statut concluant ou une recommandation change dans la chronologie serveur."
        )
    else:
        qualification = "STABLE"
        explanations.append(
            "Aucun statut concluant ni aucune recommandation ne change dans la chronologie serveur."
        )
    if ranking_changes:
        explanations.append(f"Le classement change lors de {ranking_changes} transition(s).")
    explanations.append(
        "Ce constat est descriptif et ne déclenche, n'approuve ni n'autorise aucune action."
    )
    return (
        qualification,
        points,
        transitions,
        status_changes,
        recommendation_changes,
        ranking_changes,
        churn_rate,
        longest_status,
        longest_recommendation,
        longest_unchanged,
        first_recommendation,
        last_recommendation,
        worst_coverage,
        worst_margin,
        explanations,
    )
