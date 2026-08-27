from decimal import Decimal, ROUND_HALF_UP

from .comparison import Recomputed
from .models import (
    CriterionCoverageSummary,
    DecisionCreate,
    EvaluationCriterionCoverage,
)


SIX_PLACES = Decimal("0.000001")


def _rounded(value: Decimal) -> float:
    return float(value.quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def calculate_criterion_coverage(
    recomputed: list[Recomputed],
    specifications: list[DecisionCreate],
    evaluated_at: list[str],
    compatibility: list[str],
) -> tuple[
    str,
    list[EvaluationCriterionCoverage],
    list[CriterionCoverageSummary],
    list[str],
    list[str],
    float,
    float,
    EvaluationCriterionCoverage | None,
    list[str],
]:
    if compatibility:
        return (
            "INCOMPATIBLE", [], [], [], [], 0.0, 0.0, None,
            list(compatibility)
            + [
                "Aucune couverture agrégée n'est calculée entre contrats incompatibles.",
                "Le dossier est descriptif et n'autorise aucune action.",
            ],
        )

    points: list[EvaluationCriterionCoverage] = []
    reference = specifications[0]
    measured_keys = sorted(item.key for item in reference.criteria)
    for sequence, (item, specification, timestamp) in enumerate(
        zip(recomputed, specifications, evaluated_at), start=1
    ):
        coverage_by_key: dict[str, float] = {}
        for criterion in sorted(specification.criteria, key=lambda entry: entry.key):
            qualifying = sum(
                1
                for alternative in specification.alternatives
                if any(
                    observation.alternative_key == alternative.key
                    and observation.criterion_key == criterion.key
                    and observation.confidence >= criterion.minimum_confidence
                    for observation in specification.observations
                )
            )
            coverage_by_key[criterion.key] = _rounded(
                Decimal(qualifying) / Decimal(len(specification.alternatives))
            )
        covered = sorted(key for key, value in coverage_by_key.items() if value == 1.0)
        gaps = sorted(key for key in measured_keys if coverage_by_key[key] < 1.0)
        overall = _rounded(
            sum((Decimal(str(coverage_by_key[key])) for key in measured_keys), Decimal("0"))
            / Decimal(len(measured_keys))
        )
        points.append(
            EvaluationCriterionCoverage(
                sequence=sequence,
                evaluation_id=item.snapshot.evaluation_id,
                decision_id=item.snapshot.decision_id,
                evaluated_at=timestamp,
                status=item.snapshot.status,
                covered_criterion_keys=covered,
                gap_criterion_keys=gaps,
                criterion_coverage=coverage_by_key,
                overall_coverage=overall,
                decision_hash=item.snapshot.decision_hash,
                recomputed_outcome_hash=item.snapshot.recomputed_outcome_hash,
            )
        )

    criteria: list[CriterionCoverageSummary] = []
    for criterion in sorted(reference.criteria, key=lambda entry: entry.key):
        values = [point.criterion_coverage[criterion.key] for point in points]
        gap_ids = [
            point.evaluation_id for point in points
            if point.criterion_coverage[criterion.key] < 1.0
        ]
        full_count = len(points) - len(gap_ids)
        criteria.append(
            CriterionCoverageSummary(
                criterion_key=criterion.key,
                required=criterion.required,
                minimum_confidence=criterion.minimum_confidence,
                fully_covered_evaluation_count=full_count,
                fully_covered_evaluation_share=_rounded(
                    Decimal(full_count) / Decimal(len(points))
                ),
                minimum_coverage=min(values),
                average_coverage=_rounded(
                    sum((Decimal(str(value)) for value in values), Decimal("0"))
                    / Decimal(len(values))
                ),
                gap_evaluation_ids=gap_ids,
            )
        )

    common_covered = sorted(
        item.criterion_key for item in criteria if item.fully_covered_evaluation_count == len(points)
    )
    gap_keys = sorted(
        item.criterion_key for item in criteria
        if item.fully_covered_evaluation_count < len(points)
    )
    minimum_overall = min(point.overall_coverage for point in points)
    average_overall = _rounded(
        sum((Decimal(str(point.overall_coverage)) for point in points), Decimal("0"))
        / Decimal(len(points))
    )
    worst = min(points, key=lambda point: (point.overall_coverage, point.evaluation_id))
    explanations: list[str] = []
    if any(point.status == "INSUFFICIENT" for point in points):
        qualification = "INSUFFICIENT"
        explanations.append("Au moins une évaluation recalculée est non concluante.")
    elif gap_keys:
        qualification = "PARTIAL"
        explanations.append(
            f"{len(gap_keys)} critère(s) ne sont pas intégralement couverts dans toute la série."
        )
    else:
        qualification = "COMPLETE"
        explanations.append("Tous les critères sont couverts pour toutes les alternatives et évaluations.")
    explanations.append(
        "La couverture vérifie présence et confiance minimale, pas la véracité ni l'actualité des sources."
    )
    explanations.append("Le dossier est descriptif et n'autorise aucune action.")
    return (
        qualification, points, criteria, common_covered, gap_keys,
        minimum_overall, average_overall, worst, explanations,
    )
