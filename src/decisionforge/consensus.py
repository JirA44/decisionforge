from decimal import Decimal, ROUND_HALF_UP

from .comparison import Recomputed
from .models import ConsensusAlternative, DecisionCreate


SIX_PLACES = Decimal("0.000001")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    decimals = [Decimal(str(value)) for value in values]
    return _rounded(sum(decimals, Decimal("0")) / Decimal(len(decimals)))


def _dispersion(values: list[float]) -> float | None:
    if not values:
        return None
    decimals = [Decimal(str(value)) for value in values]
    mean = sum(decimals, Decimal("0")) / Decimal(len(decimals))
    variance = sum(((value - mean) ** 2 for value in decimals), Decimal("0")) / Decimal(
        len(decimals)
    )
    return _rounded(variance.sqrt())


def consensus_compatibility_reasons(
    specifications: list[DecisionCreate], evaluation_methods: list[str]
) -> list[str]:
    reasons: list[str] = []
    reference = specifications[0]
    if len(set(evaluation_methods)) != 1:
        reasons.append("Les méthodes d'évaluation ne sont pas identiques.")

    decision_identity = (reference.title, reference.problem)
    if any((item.title, item.problem) != decision_identity for item in specifications[1:]):
        reasons.append("Les snapshots ne décrivent pas la même décision (titre et problème différents).")

    def alternatives_contract(specification: DecisionCreate) -> list[tuple[str, str]]:
        return sorted((item.key, item.label) for item in specification.alternatives)

    reference_alternatives = alternatives_contract(reference)
    if any(
        alternatives_contract(item) != reference_alternatives for item in specifications[1:]
    ):
        reasons.append("Les contrats d'alternatives (clés et libellés) ne sont pas identiques.")

    def criteria_contract(
        specification: DecisionCreate,
    ) -> list[tuple[str, str, float, bool, float, float | None]]:
        return sorted(
            (
                item.key,
                item.label,
                item.weight,
                item.required,
                item.minimum_confidence,
                item.blocking_minimum,
            )
            for item in specification.criteria
        )

    reference_criteria = criteria_contract(reference)
    if any(criteria_contract(item) != reference_criteria for item in specifications[1:]):
        reasons.append(
            "Les contrats de critères (clés, libellés, poids et seuils) ne sont pas identiques."
        )
    return reasons


def aggregate_consensus(
    recomputed: list[Recomputed], compatibility: list[str]
) -> tuple[
    str,
    int,
    str | None,
    float,
    list[ConsensusAlternative],
    float | None,
    list[str],
]:
    count = len(recomputed)
    sufficient_count = sum(item.snapshot.status != "INSUFFICIENT" for item in recomputed)
    recommendation_counts: dict[str, int] = {}
    for item in recomputed:
        key = item.snapshot.recommended_alternative_key
        if key is not None:
            recommendation_counts[key] = recommendation_counts.get(key, 0) + 1

    majority_key: str | None = None
    majority_count = 0
    if recommendation_counts:
        ordered = sorted(recommendation_counts.items(), key=lambda item: (-item[1], item[0]))
        if len(ordered) == 1 or ordered[0][1] > ordered[1][1]:
            majority_key, majority_count = ordered[0]
    majority_share = _rounded(Decimal(majority_count) / Decimal(count))

    alternatives: list[ConsensusAlternative] = []
    if not compatibility:
        alternative_keys = sorted(recomputed[0].ranking_by_key)
        for key in alternative_keys:
            entries = [item.ranking_by_key[key] for item in recomputed]
            ranks = [float(item.rank) for item in entries if item.rank is not None]
            scores = [item.score for item in entries]
            coverages = [item.coverage for item in entries]
            eligible_count = sum(item.eligible for item in entries)
            alternatives.append(
                ConsensusAlternative(
                    alternative_key=key,
                    recommendation_count=recommendation_counts.get(key, 0),
                    recommendation_share=_rounded(
                        Decimal(recommendation_counts.get(key, 0)) / Decimal(count)
                    ),
                    average_rank=_mean(ranks),
                    rank_dispersion=_dispersion(ranks),
                    average_score=_mean(scores) or 0.0,
                    score_dispersion=_dispersion(scores) or 0.0,
                    minimum_coverage=min(coverages),
                    eligible_count=eligible_count,
                    eligible_share=_rounded(Decimal(eligible_count) / Decimal(count)),
                    all_eligible=eligible_count == count,
                )
            )

    margins = [
        item.snapshot.winner_margin
        for item in recomputed
        if item.snapshot.winner_margin is not None
    ]
    minimum_winner_margin = min(margins) if margins else None
    explanations = list(compatibility)

    if compatibility:
        qualification = "INCOMPATIBLE"
        explanations.append("Aucun consensus n'est calculé à partir d'évaluations incompatibles.")
    elif sufficient_count < count:
        qualification = "INSUFFICIENT"
        explanations.append(
            f"{count - sufficient_count} évaluation(s) recalculée(s) ont des preuves insuffisantes."
        )
    elif majority_key is not None and majority_count == count:
        qualification = "CONSENSUS"
        explanations.append(
            f"Les {count} évaluations recalculées désignent toutes {majority_key}."
        )
    elif majority_key is not None and majority_count * 3 >= count * 2:
        qualification = "STABLE_MAJORITY"
        explanations.append(
            f"{majority_key} obtient une majorité stable de {majority_count}/{count} évaluations."
        )
    else:
        qualification = "DIVIDED"
        explanations.append("Aucune alternative n'atteint une part strictement exploitable de deux tiers.")

    explanations.append(
        "Le dossier est descriptif et ne constitue ni une recommandation automatique ni une autorisation d'agir."
    )
    return (
        qualification,
        sufficient_count,
        majority_key,
        majority_share,
        alternatives,
        minimum_winner_margin,
        explanations,
    )
