from decimal import Decimal, ROUND_HALF_UP

from .hashing import canonical_hash
from .models import DecisionCreate, RankedAlternative


SIX_PLACES = Decimal("0.000001")
TIE_MARGIN = Decimal("0.000001")


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _rounded(value: Decimal) -> float:
    return float(value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def evaluate(specification: DecisionCreate) -> tuple[str, str | None, list[RankedAlternative], list[str], str]:
    """Évalue une spécification de façon déterministe, sans verdict fourni par le client."""
    criteria = {criterion.key: criterion for criterion in specification.criteria}
    observations = {
        (observation.alternative_key, observation.criterion_key): observation
        for observation in specification.observations
    }
    total_weight = sum((_decimal(item.weight) for item in specification.criteria), Decimal("0"))
    computed: list[dict] = []

    for alternative in specification.alternatives:
        weighted_score = Decimal("0")
        covered_weight = Decimal("0")
        blockers: list[str] = []
        insufficiencies: list[str] = []

        for criterion_key, criterion in criteria.items():
            observation = observations.get((alternative.key, criterion_key))
            weight = _decimal(criterion.weight)
            if observation is None:
                if criterion.required:
                    insufficiencies.append(f"{criterion_key}: observation manquante")
                continue
            confidence = _decimal(observation.confidence)
            if confidence < _decimal(criterion.minimum_confidence):
                if criterion.required:
                    insufficiencies.append(
                        f"{criterion_key}: confiance {observation.confidence:g} inférieure au minimum {criterion.minimum_confidence:g}"
                    )
                continue
            covered_weight += weight
            weighted_score += weight * _decimal(observation.score) * confidence
            if criterion.blocking_minimum is not None and observation.score < criterion.blocking_minimum:
                blockers.append(
                    f"{criterion_key}: score {observation.score:g} inférieur au seuil bloquant {criterion.blocking_minimum:g}"
                )

        score = weighted_score / total_weight
        coverage = covered_weight / total_weight
        computed.append(
            {
                "alternative_key": alternative.key,
                "score_decimal": score,
                "score": _rounded(score),
                "coverage": _rounded(coverage),
                "eligible": not blockers and not insufficiencies,
                "blockers": blockers,
                "insufficiencies": insufficiencies,
            }
        )

    explanations: list[str] = []
    recommended: str | None = None
    incomplete = [row["alternative_key"] for row in computed if row["insufficiencies"]]
    eligible = [row for row in computed if row["eligible"]]

    if incomplete:
        status = "INSUFFICIENT"
        explanations.append("Éléments requis insuffisants pour : " + ", ".join(sorted(incomplete)) + ".")
    elif not eligible:
        status = "BLOCKED"
        explanations.append("Toutes les alternatives enfreignent au moins un seuil bloquant.")
    else:
        eligible_sorted = sorted(eligible, key=lambda row: (-row["score_decimal"], row["alternative_key"]))
        if len(eligible_sorted) > 1 and eligible_sorted[0]["score_decimal"] - eligible_sorted[1]["score_decimal"] <= TIE_MARGIN:
            status = "INSUFFICIENT"
            explanations.append("Les meilleures alternatives sont à égalité ; aucun choix unique n'est affirmé.")
        else:
            status = "RECOMMENDED"
            recommended = eligible_sorted[0]["alternative_key"]
            explanations.append(f"{recommended} obtient le meilleur score pondéré parmi les alternatives admissibles.")

    order = sorted(computed, key=lambda row: (not row["eligible"], -row["score_decimal"], row["alternative_key"]))
    next_rank = 1
    previous_score: Decimal | None = None
    previous_rank: int | None = None
    for row in order:
        if not row["eligible"]:
            row["rank"] = None
            continue
        if previous_score is not None and row["score_decimal"] == previous_score:
            row["rank"] = previous_rank
        else:
            row["rank"] = next_rank
            previous_rank = next_rank
        previous_score = row["score_decimal"]
        next_rank += 1

    ranking = [
        RankedAlternative(
            alternative_key=row["alternative_key"],
            score=row["score"],
            coverage=row["coverage"],
            eligible=row["eligible"],
            rank=row["rank"],
            blockers=row["blockers"],
            insufficiencies=row["insufficiencies"],
        )
        for row in order
    ]
    outcome = {
        "status": status,
        "recommended_alternative_key": recommended,
        "ranking": [item.model_dump(mode="json") for item in ranking],
        "explanations": explanations,
        "method": "weighted-evidence-v1",
    }
    return status, recommended, ranking, explanations, canonical_hash(outcome)
