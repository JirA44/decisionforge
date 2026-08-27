from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AlternativeCreate(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


class CriterionCreate(StrictModel):
    key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    label: str = Field(min_length=1, max_length=200)
    weight: float = Field(gt=0, le=1)
    required: bool = True
    minimum_confidence: float = Field(default=0.70, ge=0, le=1)
    blocking_minimum: float | None = Field(default=None, ge=0, le=100)


class ObservationCreate(StrictModel):
    alternative_key: str = Field(min_length=1, max_length=64)
    criterion_key: str = Field(min_length=1, max_length=64)
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    source_ref: str = Field(min_length=1, max_length=1000)
    note: str = Field(default="", max_length=2000)


class ForecastOutcomeCreate(StrictModel):
    predicted_probabilities: dict[str, float] = Field(min_length=2, max_length=20)
    observed_alternative_key: str = Field(min_length=1, max_length=64)
    prediction_ref: str = Field(min_length=1, max_length=1000)
    outcome_ref: str = Field(min_length=1, max_length=1000)


class DecisionCreate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    problem: str = Field(min_length=1, max_length=5000)
    context: str = Field(default="", max_length=5000)
    alternatives: list[AlternativeCreate] = Field(min_length=2, max_length=20)
    criteria: list[CriterionCreate] = Field(min_length=1, max_length=20)
    observations: list[ObservationCreate] = Field(default_factory=list, max_length=400)
    forecast_outcome: ForecastOutcomeCreate | None = None

    @model_validator(mode="after")
    def validate_references_and_uniqueness(self):
        alternative_keys = [item.key for item in self.alternatives]
        criterion_keys = [item.key for item in self.criteria]
        if len(alternative_keys) != len(set(alternative_keys)):
            raise ValueError("alternative keys must be unique")
        if len(criterion_keys) != len(set(criterion_keys)):
            raise ValueError("criterion keys must be unique")
        valid_alternatives = set(alternative_keys)
        valid_criteria = set(criterion_keys)
        pairs: set[tuple[str, str]] = set()
        for observation in self.observations:
            if observation.alternative_key not in valid_alternatives:
                raise ValueError(f"unknown alternative: {observation.alternative_key}")
            if observation.criterion_key not in valid_criteria:
                raise ValueError(f"unknown criterion: {observation.criterion_key}")
            pair = (observation.alternative_key, observation.criterion_key)
            if pair in pairs:
                raise ValueError("one observation per alternative/criterion pair is allowed")
            pairs.add(pair)
        if self.forecast_outcome is not None:
            probability_keys = set(self.forecast_outcome.predicted_probabilities)
            if probability_keys != valid_alternatives:
                raise ValueError("predicted probability keys must match all alternative keys")
            if any(
                probability < 0 or probability > 1
                for probability in self.forecast_outcome.predicted_probabilities.values()
            ):
                raise ValueError("predicted probabilities must be between 0 and 1")
            probability_sum = sum(self.forecast_outcome.predicted_probabilities.values())
            if abs(probability_sum - 1.0) > 0.000001:
                raise ValueError("predicted probabilities must sum to 1")
            if self.forecast_outcome.observed_alternative_key not in valid_alternatives:
                raise ValueError("observed outcome must reference an alternative")
        return self


class DecisionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    input_hash: str
    specification: DecisionCreate
    immutable: bool = True
    created_at: str


class EvaluationCreate(StrictModel):
    decision_id: str = Field(min_length=1)
    method: Literal["weighted-evidence-v1"] = "weighted-evidence-v1"


class RankedAlternative(BaseModel):
    alternative_key: str
    score: float
    coverage: float
    eligible: bool
    rank: int | None
    blockers: list[str]
    insufficiencies: list[str]


class Evaluation(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    decision_id: str
    method: str
    status: Literal["RECOMMENDED", "BLOCKED", "INSUFFICIENT"]
    recommended_alternative_key: str | None
    ranking: list[RankedAlternative]
    explanations: list[str]
    decision_hash: str
    outcome_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    created_at: str
    warning: str = (
        "Recommandation calculée à partir des données fournies ; elle ne prouve ni leur exactitude "
        "ni l'absence de risques externes. Une validation humaine reste nécessaire."
    )


class AuditEvent(BaseModel):
    sequence: int
    event_type: str
    entity_type: str
    entity_id: str
    payload: dict
    created_at: str


class SensitivityAnalysisCreate(StrictModel):
    evaluation_id: str = Field(min_length=1)
    method: Literal["weight-sensitivity-v1"] = "weight-sensitivity-v1"
    policy: Literal["bounded-oat-10pct-v1"] = "bounded-oat-10pct-v1"


class SensitivityScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    criterion_key: str | None
    direction: Literal["BASELINE", "DECREASE", "INCREASE"]
    normalized_weights: dict[str, float]
    evaluation_status: Literal["RECOMMENDED", "BLOCKED", "INSUFFICIENT"]
    winner_alternative_key: str | None
    winner_margin: float | None
    ranking: list[RankedAlternative]


class SensitivityAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_id: str
    decision_id: str
    method: str
    policy: str
    qualification: Literal["ROBUST", "FRAGILE", "INSUFFICIENT"]
    baseline_winner_alternative_key: str | None
    winner_stability: float
    minimum_winner_margin: float | None
    scenarios: list[SensitivityScenario]
    reasons: list[str]
    evaluation_hash: str
    analysis_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    created_at: str
    warning: str = (
        "Cette analyse de sensibilité décrit uniquement la stabilité sous la politique de perturbation "
        "indiquée. Elle ne déclenche aucune action et ne remplace pas une validation humaine."
    )


class DecisionComparisonCreate(StrictModel):
    baseline_evaluation_id: str = Field(min_length=1)
    candidate_evaluation_id: str = Field(min_length=1)


class RecomputedEvaluationSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evaluation_id: str
    decision_id: str
    evaluation_method: str
    status: Literal["RECOMMENDED", "BLOCKED", "INSUFFICIENT"]
    recommended_alternative_key: str | None
    ranking: list[RankedAlternative]
    winner_margin: float | None
    decision_hash: str
    recomputed_outcome_hash: str


class AlternativeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alternative_key: str
    baseline_rank: int | None
    candidate_rank: int | None
    rank_change: int | None
    baseline_score: float
    candidate_score: float
    score_change: float
    baseline_coverage: float
    candidate_coverage: float
    coverage_change: float
    eligibility_changed: bool


class DecisionComparison(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    baseline_evaluation_id: str
    candidate_evaluation_id: str
    method: str
    qualification: Literal["CONSISTENT", "CHANGED", "INCOMPATIBLE", "INSUFFICIENT"]
    compatible: bool
    baseline: RecomputedEvaluationSnapshot
    candidate: RecomputedEvaluationSnapshot
    recommendation_changed: bool
    status_changed: bool
    ranking_changed: bool
    winner_margin_change: float | None
    alternatives: list[AlternativeComparison]
    explanations: list[str]
    comparison_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    created_at: str
    warning: str = (
        "Cette comparaison est descriptive, repose uniquement sur les snapshots fournis et ne déclenche "
        "ni n'autorise aucune action. Une validation humaine reste nécessaire."
    )


class ConsensusDossierCreate(StrictModel):
    evaluation_ids: list[str] = Field(min_length=3, max_length=50)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(not item.strip() for item in self.evaluation_ids):
            raise ValueError("evaluation ids must not be blank")
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation ids must be unique")
        return self


class ConsensusAlternative(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alternative_key: str
    recommendation_count: int
    recommendation_share: float
    average_rank: float | None
    rank_dispersion: float | None
    average_score: float
    score_dispersion: float
    minimum_coverage: float
    eligible_count: int
    eligible_share: float
    all_eligible: bool


class ConsensusDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_ids: list[str]
    method: str
    evaluation_method: str
    qualification: Literal[
        "CONSENSUS", "STABLE_MAJORITY", "DIVIDED", "INSUFFICIENT", "INCOMPATIBLE"
    ]
    compatible: bool
    evaluation_count: int
    sufficient_evaluation_count: int
    majority_alternative_key: str | None
    majority_share: float
    evaluations: list[RecomputedEvaluationSnapshot]
    alternatives: list[ConsensusAlternative]
    minimum_winner_margin: float | None
    explanations: list[str]
    input_hash: str
    dossier_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    created_at: str
    warning: str = (
        "Ce dossier décrit un accord statistique entre évaluations compatibles. Il ne produit aucune "
        "recommandation opérationnelle et ne déclenche, n'approuve ni n'autorise aucune action."
    )


class CalibrationDossierCreate(StrictModel):
    evaluation_ids: list[str] = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(not item.strip() for item in self.evaluation_ids):
            raise ValueError("evaluation ids must not be blank")
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation ids must be unique")
        return self


class CalibrationEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evaluation_id: str
    decision_id: str
    predicted_alternative_key: str
    observed_alternative_key: str
    confidence: float
    observed_probability: float
    correct: bool
    recomputed_outcome_hash: str


class CalibrationBin(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    index: int
    lower_bound: float
    upper_bound: float
    count: int
    average_confidence: float | None
    observed_accuracy: float | None
    calibration_gap: float | None


class CalibrationDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_ids: list[str]
    method: str
    qualification: Literal["CALIBRATED", "MISALIGNED", "INSUFFICIENT", "INCOMPATIBLE"]
    compatible: bool
    evaluation_count: int
    usable_evaluation_count: int
    coverage: float
    brier_score: float | None
    bounded_log_loss: float | None
    expected_calibration_error: float | None
    resolution: float | None
    worst_bin_index: int | None
    evaluations: list[CalibrationEvaluation]
    bins: list[CalibrationBin]
    explanations: list[str]
    input_hash: str
    dossier_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    created_at: str
    warning: str = (
        "Ce dossier mesure une calibration historique. Il ne prédit pas une performance future et ne "
        "déclenche, n'approuve ni n'autorise aucune action."
    )


class DecisionStabilityDossierCreate(StrictModel):
    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(not item.strip() for item in self.evaluation_ids):
            raise ValueError("evaluation ids must not be blank")
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation ids must be unique")
        return self


class DecisionStabilityPoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int
    evaluation_id: str
    decision_id: str
    evaluated_at: str
    status: Literal["RECOMMENDED", "BLOCKED", "INSUFFICIENT"]
    recommended_alternative_key: str | None
    ranks: dict[str, int | None]
    minimum_coverage: float
    winner_margin: float | None
    decision_hash: str
    recomputed_outcome_hash: str


class DecisionStabilityTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int
    from_evaluation_id: str
    to_evaluation_id: str
    status_changed: bool
    recommendation_changed: bool
    ranking_changed: bool
    moved_alternatives: list[str]


class DecisionStabilityDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_ids: list[str]
    chronological_evaluation_ids: list[str]
    method: str
    evaluation_method: str
    qualification: Literal["STABLE", "DRIFTING", "INSUFFICIENT", "INCOMPATIBLE"]
    compatible: bool
    evaluation_count: int
    transition_count: int
    status_transition_count: int
    recommendation_transition_count: int
    ranking_transition_count: int
    churn_rate: float
    longest_status_streak: int
    longest_recommendation_streak: int
    longest_unchanged_streak: int
    first_recommendation: str | None
    last_recommendation: str | None
    worst_coverage: float
    worst_winner_margin: float | None
    evaluations: list[DecisionStabilityPoint]
    transitions: list[DecisionStabilityTransition]
    explanations: list[str]
    input_hash: str
    evidence_hash: str
    dossier_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    automatic_action: bool = False
    created_at: str
    warning: str = (
        "Ce dossier décrit une stabilité chronologique à partir de preuves persistées. Il ne déclenche, "
        "n'approuve ni n'autorise aucune action et requiert une interprétation humaine."
    )


class DecisionChangeAttributionDossierCreate(StrictModel):
    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(not item.strip() for item in self.evaluation_ids):
            raise ValueError("evaluation ids must not be blank")
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation ids must be unique")
        return self


class ObservationContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alternative_key: str
    criterion_key: str
    before_score: float | None
    after_score: float | None
    before_confidence: float | None
    after_confidence: float | None
    before_weighted_component: float
    after_weighted_component: float
    delta: float
    comparable: bool
    source_changed: bool


class CriterionContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    criterion_key: str
    net_effect: float
    absolute_effect: float
    observation_change_count: int
    comparable: bool


class DecisionChangeAttributionTransition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int
    from_evaluation_id: str
    to_evaluation_id: str
    status_changed: bool
    recommendation_changed: bool
    ranking_changed: bool
    change_detected: bool
    winning_alternative_key: str | None
    losing_alternative_key: str | None
    alternative_score_deltas: dict[str, float]
    observation_contributions: list[ObservationContribution]
    criterion_contributions: list[CriterionContribution]
    dominant_criteria: list[str]
    change_magnitude: float
    explained: bool
    explanation_completeness: float
    unexplained_reasons: list[str]


class DecisionChangeAttributionDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_ids: list[str]
    chronological_evaluation_ids: list[str]
    method: str
    evaluation_method: str
    qualification: Literal["EXPLAINED", "PARTIAL", "INSUFFICIENT", "INCOMPATIBLE"]
    compatible: bool
    evaluation_count: int
    transition_count: int
    changed_transition_count: int
    explained_change_count: int
    unexplained_change_count: int
    dominant_criteria: list[str]
    winning_alternatives: list[str]
    losing_alternatives: list[str]
    worst_transition: DecisionChangeAttributionTransition | None
    evaluations: list[RecomputedEvaluationSnapshot]
    transitions: list[DecisionChangeAttributionTransition]
    explanations: list[str]
    input_hash: str
    evidence_hash: str
    dossier_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    automatic_action: bool = False
    created_at: str
    warning: str = (
        "Cette attribution décrit des contributions calculées à partir des observations persistées. "
        "Elle n'établit pas une causalité externe et ne déclenche, n'approuve ni n'autorise aucune action."
    )


class CriterionCoverageDossierCreate(StrictModel):
    evaluation_ids: list[str] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def validate_unique_ids(self):
        if any(not item.strip() for item in self.evaluation_ids):
            raise ValueError("evaluation ids must not be blank")
        if len(self.evaluation_ids) != len(set(self.evaluation_ids)):
            raise ValueError("evaluation ids must be unique")
        return self


class EvaluationCriterionCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sequence: int
    evaluation_id: str
    decision_id: str
    evaluated_at: str
    status: Literal["RECOMMENDED", "BLOCKED", "INSUFFICIENT"]
    covered_criterion_keys: list[str]
    gap_criterion_keys: list[str]
    criterion_coverage: dict[str, float]
    overall_coverage: float
    decision_hash: str
    recomputed_outcome_hash: str


class CriterionCoverageSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    criterion_key: str
    required: bool
    minimum_confidence: float
    fully_covered_evaluation_count: int
    fully_covered_evaluation_share: float
    minimum_coverage: float
    average_coverage: float
    gap_evaluation_ids: list[str]


class CriterionCoverageDossier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    evaluation_ids: list[str]
    chronological_evaluation_ids: list[str]
    method: str
    evaluation_method: str
    qualification: Literal["COMPLETE", "PARTIAL", "INSUFFICIENT", "INCOMPATIBLE"]
    compatible: bool
    evaluation_count: int
    criterion_count: int
    required_criterion_count: int
    common_covered_criterion_keys: list[str]
    gap_criterion_keys: list[str]
    minimum_overall_coverage: float
    average_overall_coverage: float
    worst_evaluation: EvaluationCriterionCoverage | None
    evaluations: list[EvaluationCriterionCoverage]
    criteria: list[CriterionCoverageSummary]
    explanations: list[str]
    input_hash: str
    evidence_hash: str
    dossier_hash: str
    reproducible: bool = True
    idempotent_replay: bool = False
    immutable: bool = True
    automatic_action: bool = False
    created_at: str
    warning: str = (
        "Ce dossier mesure uniquement la couverture des critères par les observations persistées. "
        "Il ne certifie pas les sources et ne déclenche, n'approuve ni n'autorise aucune action."
    )
