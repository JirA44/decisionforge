from decimal import Decimal, ROUND_HALF_UP

from .comparison import Recomputed
from .models import (
    CriterionContribution,
    DecisionChangeAttributionTransition,
    DecisionCreate,
    ObservationContribution,
)


SIX_PLACES = Decimal("0.000001")
EPSILON = Decimal("0.000001")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def _component(specification: DecisionCreate, alternative: str, criterion_key: str) -> Decimal:
    criterion = next(item for item in specification.criteria if item.key == criterion_key)
    observation = next(
        (
            item
            for item in specification.observations
            if item.alternative_key == alternative and item.criterion_key == criterion_key
        ),
        None,
    )
    if observation is None or observation.confidence < criterion.minimum_confidence:
        return Decimal("0")
    total_weight = sum((Decimal(str(item.weight)) for item in specification.criteria), Decimal("0"))
    return (
        Decimal(str(criterion.weight))
        * Decimal(str(observation.score))
        * Decimal(str(observation.confidence))
        / total_weight
    )


def _observation(specification: DecisionCreate, alternative: str, criterion: str):
    return next(
        (
            item
            for item in specification.observations
            if item.alternative_key == alternative and item.criterion_key == criterion
        ),
        None,
    )


def attribute_changes(
    recomputed: list[Recomputed],
    specifications: list[DecisionCreate],
    compatibility: list[str],
) -> tuple[
    str,
    list[DecisionChangeAttributionTransition],
    int,
    int,
    int,
    list[str],
    list[str],
    list[str],
    DecisionChangeAttributionTransition | None,
    list[str],
]:
    if compatibility:
        return (
            "INCOMPATIBLE",
            [],
            0,
            0,
            0,
            [],
            [],
            [],
            None,
            list(compatibility)
            + [
                "Aucune attribution n'est calculée entre décisions incompatibles.",
                "L'attribution est descriptive et n'autorise aucune action.",
            ],
        )
    transitions: list[DecisionChangeAttributionTransition] = []
    criterion_totals: dict[str, Decimal] = {}
    for index, ((before, after), (before_spec, after_spec)) in enumerate(
        zip(zip(recomputed, recomputed[1:]), zip(specifications, specifications[1:])), start=1
    ):
        before_snapshot = before.snapshot
        after_snapshot = after.snapshot
        before_ranks = {item.alternative_key: item.rank for item in before_snapshot.ranking}
        after_ranks = {item.alternative_key: item.rank for item in after_snapshot.ranking}
        status_changed = before_snapshot.status != after_snapshot.status
        recommendation_changed = (
            before_snapshot.recommended_alternative_key
            != after_snapshot.recommended_alternative_key
        )
        ranking_changed = before_ranks != after_ranks
        change_detected = status_changed or recommendation_changed or ranking_changed
        winner = after_snapshot.recommended_alternative_key
        loser = before_snapshot.recommended_alternative_key
        before_scores = {item.alternative_key: Decimal(str(item.score)) for item in before_snapshot.ranking}
        after_scores = {item.alternative_key: Decimal(str(item.score)) for item in after_snapshot.ranking}
        alternative_deltas = {
            key: _rounded(after_scores[key] - before_scores[key]) for key in sorted(before_scores)
        }

        observations: list[ObservationContribution] = []
        per_criterion: dict[str, list[ObservationContribution]] = {}
        for criterion in before_spec.criteria:
            for alternative in sorted(before_scores):
                before_observation = _observation(before_spec, alternative, criterion.key)
                after_observation = _observation(after_spec, alternative, criterion.key)
                before_component = _component(before_spec, alternative, criterion.key)
                after_component = _component(after_spec, alternative, criterion.key)
                item = ObservationContribution(
                    alternative_key=alternative,
                    criterion_key=criterion.key,
                    before_score=before_observation.score if before_observation else None,
                    after_score=after_observation.score if after_observation else None,
                    before_confidence=before_observation.confidence if before_observation else None,
                    after_confidence=after_observation.confidence if after_observation else None,
                    before_weighted_component=_rounded(before_component),
                    after_weighted_component=_rounded(after_component),
                    delta=_rounded(after_component - before_component),
                    comparable=before_observation is not None and after_observation is not None,
                    source_changed=(
                        (before_observation.source_ref if before_observation else None)
                        != (after_observation.source_ref if after_observation else None)
                    ),
                )
                observations.append(item)
                per_criterion.setdefault(criterion.key, []).append(item)

        criteria: list[CriterionContribution] = []
        for criterion_key, items in per_criterion.items():
            deltas = {item.alternative_key: Decimal(str(item.delta)) for item in items}
            if winner is not None and loser is not None and winner != loser:
                net_effect = deltas[winner] - deltas[loser]
            else:
                net_effect = sum(deltas.values(), Decimal("0"))
            absolute_effect = sum((abs(value) for value in deltas.values()), Decimal("0"))
            changed_items = [
                item for item in items if abs(Decimal(str(item.delta))) > EPSILON or item.source_changed
            ]
            contribution = CriterionContribution(
                criterion_key=criterion_key,
                net_effect=_rounded(net_effect),
                absolute_effect=_rounded(absolute_effect),
                observation_change_count=len(changed_items),
                comparable=all(item.comparable for item in changed_items),
            )
            criteria.append(contribution)
            criterion_totals[criterion_key] = criterion_totals.get(criterion_key, Decimal("0")) + absolute_effect
        criteria.sort(key=lambda item: (-item.absolute_effect, item.criterion_key))
        dominant = [item.criterion_key for item in criteria if item.absolute_effect > float(EPSILON)][:3]
        changed_observations = [
            item
            for item in observations
            if abs(Decimal(str(item.delta))) > EPSILON or item.source_changed
        ]
        comparable_count = sum(item.comparable for item in changed_observations)
        completeness = (
            Decimal(comparable_count) / Decimal(len(changed_observations))
            if changed_observations
            else Decimal("1" if not change_detected else "0")
        )
        unexplained: list[str] = []
        if change_detected and not changed_observations:
            unexplained.append("Aucune variation d'observation persistée n'attribue le changement calculé.")
        if change_detected and comparable_count < len(changed_observations):
            unexplained.append(
                "Au moins une contribution repose sur une observation absente d'un côté de la transition."
            )
        explained = not unexplained
        magnitude = max((abs(value) for value in alternative_deltas.values()), default=0.0)
        transitions.append(
            DecisionChangeAttributionTransition(
                sequence=index,
                from_evaluation_id=before_snapshot.evaluation_id,
                to_evaluation_id=after_snapshot.evaluation_id,
                status_changed=status_changed,
                recommendation_changed=recommendation_changed,
                ranking_changed=ranking_changed,
                change_detected=change_detected,
                winning_alternative_key=winner if recommendation_changed else None,
                losing_alternative_key=loser if recommendation_changed else None,
                alternative_score_deltas=alternative_deltas,
                observation_contributions=observations,
                criterion_contributions=criteria,
                dominant_criteria=dominant,
                change_magnitude=magnitude,
                explained=explained,
                explanation_completeness=_rounded(completeness),
                unexplained_reasons=unexplained,
            )
        )

    changed = [item for item in transitions if item.change_detected]
    explained_count = sum(item.explained for item in changed)
    unexplained_count = len(changed) - explained_count
    dominant_criteria = [
        key for key, _ in sorted(criterion_totals.items(), key=lambda item: (-item[1], item[0]))
        if criterion_totals[key] > EPSILON
    ]
    winners = sorted(
        {item.winning_alternative_key for item in transitions if item.winning_alternative_key is not None}
    )
    losers = sorted(
        {item.losing_alternative_key for item in transitions if item.losing_alternative_key is not None}
    )
    worst = max(transitions, key=lambda item: (item.change_magnitude, item.sequence), default=None)
    explanations = list(compatibility)
    if compatibility:
        qualification = "INCOMPATIBLE"
        explanations.append("Aucune attribution n'est calculée entre décisions incompatibles.")
    elif any(item.snapshot.status == "INSUFFICIENT" for item in recomputed):
        qualification = "INSUFFICIENT"
        explanations.append("Au moins une évaluation recalculée manque de preuves concluantes.")
    elif unexplained_count:
        qualification = "PARTIAL"
        explanations.append(
            f"{unexplained_count} transition(s) changée(s) ne sont attribuées que partiellement."
        )
    else:
        qualification = "EXPLAINED"
        explanations.append(
            "Toutes les transitions changées sont attribuées aux observations et critères persistés."
            if changed
            else "Aucun changement de statut, recommandation ou rang ne nécessite d'attribution."
        )
    explanations.append(
        "L'attribution est descriptive, n'établit pas une causalité externe et n'autorise aucune action."
    )
    return (
        qualification,
        transitions,
        len(changed),
        explained_count,
        unexplained_count,
        dominant_criteria,
        winners,
        losers,
        worst,
        explanations,
    )
