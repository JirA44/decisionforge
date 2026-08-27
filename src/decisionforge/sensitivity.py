from decimal import Decimal, ROUND_HALF_UP

from .evaluator import evaluate
from .models import DecisionCreate, SensitivityScenario


WEIGHT_QUANTUM = Decimal("0.000000000001")
METRIC_QUANTUM = Decimal("0.000001")
PERTURBATION = Decimal("0.10")
MIN_ROBUST_MARGIN = Decimal("1.000000")
POLICY = "bounded-oat-10pct-v1"


def _rounded_metric(value: Decimal) -> float:
    return float(value.quantize(METRIC_QUANTUM, rounding=ROUND_HALF_UP))


def _normalized_weights(
    specification: DecisionCreate,
    criterion_key: str | None = None,
    factor: Decimal = Decimal("1"),
) -> dict[str, float]:
    raw = []
    for criterion in specification.criteria:
        weight = Decimal(str(criterion.weight))
        if criterion.key == criterion_key:
            weight *= factor
        raw.append((criterion.key, weight))
    total = sum((weight for _, weight in raw), Decimal("0"))
    normalized: dict[str, float] = {}
    accumulated = Decimal("0")
    for index, (key, weight) in enumerate(raw):
        if index == len(raw) - 1:
            value = Decimal("1") - accumulated
        else:
            value = (weight / total).quantize(WEIGHT_QUANTUM, rounding=ROUND_HALF_UP)
            accumulated += value
        normalized[key] = float(value)
    return normalized


def _scenario(
    specification: DecisionCreate,
    scenario_id: str,
    criterion_key: str | None,
    direction: str,
    factor: Decimal,
) -> SensitivityScenario:
    weights = _normalized_weights(specification, criterion_key, factor)
    perturbed_payload = specification.model_dump(mode="json")
    for criterion in perturbed_payload["criteria"]:
        criterion["weight"] = weights[criterion["key"]]
    perturbed = DecisionCreate.model_validate(perturbed_payload)
    status, winner, ranking, _, _ = evaluate(perturbed)
    eligible = sorted(
        (item for item in ranking if item.eligible),
        key=lambda item: (-item.score, item.alternative_key),
    )
    margin = None
    if status == "RECOMMENDED" and len(eligible) >= 2:
        margin = _rounded_metric(Decimal(str(eligible[0].score)) - Decimal(str(eligible[1].score)))
    return SensitivityScenario(
        scenario_id=scenario_id,
        criterion_key=criterion_key,
        direction=direction,
        normalized_weights=weights,
        evaluation_status=status,
        winner_alternative_key=winner,
        winner_margin=margin,
        ranking=ranking,
    )


def analyze_sensitivity(
    specification: DecisionCreate,
) -> tuple[str, str | None, float, float | None, list[SensitivityScenario], list[str]]:
    """Applique la politique OAT ±10 % et qualifie prudemment la stabilité du gagnant."""
    scenarios = [
        _scenario(specification, "baseline", None, "BASELINE", Decimal("1")),
    ]
    for criterion in specification.criteria:
        scenarios.append(
            _scenario(
                specification,
                f"{criterion.key}:decrease-10pct",
                criterion.key,
                "DECREASE",
                Decimal("1") - PERTURBATION,
            )
        )
        scenarios.append(
            _scenario(
                specification,
                f"{criterion.key}:increase-10pct",
                criterion.key,
                "INCREASE",
                Decimal("1") + PERTURBATION,
            )
        )

    baseline = scenarios[0]
    baseline_winner = baseline.winner_alternative_key
    perturbations = scenarios[1:]
    stable_count = sum(
        scenario.evaluation_status == "RECOMMENDED"
        and scenario.winner_alternative_key == baseline_winner
        for scenario in perturbations
    )
    stability = _rounded_metric(Decimal(stable_count) / Decimal(len(perturbations))) if perturbations else 0.0
    margins = [scenario.winner_margin for scenario in scenarios if scenario.winner_margin is not None]
    minimum_margin = min(margins) if margins else None
    reasons: list[str] = []

    if baseline.evaluation_status != "RECOMMENDED" or baseline_winner is None:
        qualification = "INSUFFICIENT"
        reasons.append("L'évaluation de référence ne désigne pas de gagnant unique.")
    elif len(specification.criteria) < 2:
        qualification = "INSUFFICIENT"
        reasons.append("Au moins deux critères sont nécessaires pour tester une redistribution des poids.")
    elif stable_count != len(perturbations):
        qualification = "FRAGILE"
        changed = [
            scenario.scenario_id
            for scenario in perturbations
            if scenario.evaluation_status != "RECOMMENDED"
            or scenario.winner_alternative_key != baseline_winner
        ]
        reasons.append("Le gagnant de référence n'est pas conservé dans tous les scénarios : " + ", ".join(changed) + ".")
    elif minimum_margin is None or minimum_margin <= 0:
        qualification = "INSUFFICIENT"
        reasons.append("La marge entre les deux premières alternatives ne peut pas être établie positivement.")
    elif Decimal(str(minimum_margin)) < MIN_ROBUST_MARGIN:
        qualification = "FRAGILE"
        reasons.append(
            f"Le gagnant reste identique, mais la marge minimale de {minimum_margin:g} point est "
            f"inférieure au garde-fou prudent de {MIN_ROBUST_MARGIN:g} point."
        )
    else:
        qualification = "ROBUST"
        reasons.append(
            f"Le gagnant {baseline_winner} reste premier dans les {len(perturbations)} perturbations bornées."
        )
        reasons.append(f"La marge minimale observée est de {minimum_margin:g} points.")

    return qualification, baseline_winner, stability, minimum_margin, scenarios, reasons
