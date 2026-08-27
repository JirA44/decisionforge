import math
from decimal import Decimal, ROUND_HALF_UP

from .comparison import Recomputed
from .models import CalibrationBin, CalibrationEvaluation, DecisionCreate


BIN_COUNT = 10
MIN_CALIBRATION_EVALUATIONS = 30
LOG_LOSS_EPSILON = 1e-9
MAX_BOUNDED_LOG_LOSS = 20.0
CALIBRATED_MAX_BRIER = 0.25
CALIBRATED_MAX_LOG_LOSS = 0.70
CALIBRATED_MAX_ECE = 0.10
CALIBRATED_MAX_WORST_BIN_GAP = 0.20
SIX_PLACES = Decimal("0.000001")


def _rounded(value: float | Decimal) -> float:
    return float(Decimal(str(value)).quantize(SIX_PLACES, rounding=ROUND_HALF_UP))


def calculate_calibration(
    specifications: list[DecisionCreate],
    recomputed: list[Recomputed],
    compatibility: list[str],
) -> tuple[
    str,
    list[CalibrationEvaluation],
    list[CalibrationBin],
    float,
    float | None,
    float | None,
    float | None,
    float | None,
    int | None,
    list[str],
]:
    records: list[CalibrationEvaluation] = []
    probability_sets: list[dict[str, float]] = []
    outcomes: list[str] = []
    for specification, result in zip(specifications, recomputed):
        forecast = specification.forecast_outcome
        if forecast is None:
            continue
        probabilities = forecast.predicted_probabilities
        predicted = sorted(probabilities, key=lambda key: (-probabilities[key], key))[0]
        observed = forecast.observed_alternative_key
        records.append(
            CalibrationEvaluation(
                evaluation_id=result.snapshot.evaluation_id,
                decision_id=result.snapshot.decision_id,
                predicted_alternative_key=predicted,
                observed_alternative_key=observed,
                confidence=_rounded(probabilities[predicted]),
                observed_probability=_rounded(probabilities[observed]),
                correct=predicted == observed,
                recomputed_outcome_hash=result.snapshot.recomputed_outcome_hash,
            )
        )
        probability_sets.append(probabilities)
        outcomes.append(observed)

    total_count = len(specifications)
    usable_count = len(records)
    coverage = _rounded(usable_count / total_count)
    bins: list[CalibrationBin] = []
    brier_score = None
    log_loss = None
    expected_calibration_error = None
    resolution = None
    worst_bin_index = None

    if usable_count:
        alternative_count = len(probability_sets[0])
        brier_values = []
        log_values = []
        for probabilities, observed in zip(probability_sets, outcomes):
            squared_error = sum(
                (probability - (1.0 if key == observed else 0.0)) ** 2
                for key, probability in probabilities.items()
            ) / alternative_count
            brier_values.append(squared_error)
            observed_probability = max(probabilities[observed], LOG_LOSS_EPSILON)
            log_values.append(min(-math.log(observed_probability), MAX_BOUNDED_LOG_LOSS))
        brier_score = _rounded(sum(brier_values) / usable_count)
        log_loss = _rounded(sum(log_values) / usable_count)

        overall_accuracy = sum(record.correct for record in records) / usable_count
        weighted_gap = 0.0
        weighted_resolution = 0.0
        worst_gap = -1.0
        for index in range(BIN_COUNT):
            lower = index / BIN_COUNT
            upper = (index + 1) / BIN_COUNT
            members = [
                record
                for record in records
                if min(int(record.confidence * BIN_COUNT), BIN_COUNT - 1) == index
            ]
            if members:
                average_confidence = sum(item.confidence for item in members) / len(members)
                observed_accuracy = sum(item.correct for item in members) / len(members)
                gap = abs(average_confidence - observed_accuracy)
                weight = len(members) / usable_count
                weighted_gap += weight * gap
                weighted_resolution += weight * (observed_accuracy - overall_accuracy) ** 2
                if gap > worst_gap:
                    worst_gap = gap
                    worst_bin_index = index
                bins.append(
                    CalibrationBin(
                        index=index,
                        lower_bound=_rounded(lower),
                        upper_bound=_rounded(upper),
                        count=len(members),
                        average_confidence=_rounded(average_confidence),
                        observed_accuracy=_rounded(observed_accuracy),
                        calibration_gap=_rounded(gap),
                    )
                )
            else:
                bins.append(
                    CalibrationBin(
                        index=index,
                        lower_bound=_rounded(lower),
                        upper_bound=_rounded(upper),
                        count=0,
                        average_confidence=None,
                        observed_accuracy=None,
                        calibration_gap=None,
                    )
                )
        expected_calibration_error = _rounded(weighted_gap)
        resolution = _rounded(weighted_resolution)

    explanations = list(compatibility)
    if compatibility:
        qualification = "INCOMPATIBLE"
        explanations.append("Les décisions ou contrats ne permettent pas une calibration commune.")
    elif coverage < 1.0:
        qualification = "INSUFFICIENT"
        explanations.append(
            f"Seulement {usable_count}/{total_count} évaluations possèdent probabilités et résultat observé."
        )
    elif usable_count < MIN_CALIBRATION_EVALUATIONS:
        qualification = "INSUFFICIENT"
        explanations.append(
            f"Au moins {MIN_CALIBRATION_EVALUATIONS} évaluations complètes sont requises ; {usable_count} reçues."
        )
    else:
        worst_gap = bins[worst_bin_index].calibration_gap if worst_bin_index is not None else None
        calibrated = (
            brier_score is not None
            and brier_score <= CALIBRATED_MAX_BRIER
            and log_loss is not None
            and log_loss <= CALIBRATED_MAX_LOG_LOSS
            and expected_calibration_error is not None
            and expected_calibration_error <= CALIBRATED_MAX_ECE
            and worst_gap is not None
            and worst_gap <= CALIBRATED_MAX_WORST_BIN_GAP
        )
        qualification = "CALIBRATED" if calibrated else "MISALIGNED"
        explanations.append(
            "Seuils CALIBRATED : Brier normalisé ≤ 0,25, log loss bornée ≤ 0,70, "
            "erreur de calibration ≤ 0,10 et pire bin ≤ 0,20."
        )
        if calibrated:
            explanations.append("Toutes les métriques franchissent les seuils fixes de calibration.")
        else:
            explanations.append("Au moins une métrique dépasse un seuil fixe de calibration.")
    explanations.append(
        "Le dossier mesure un historique et ne constitue ni un verdict opérationnel ni une autorisation d'agir."
    )
    return (
        qualification,
        records,
        bins,
        coverage,
        brier_score,
        log_loss,
        expected_calibration_error,
        resolution,
        worst_bin_index,
        explanations,
    )
