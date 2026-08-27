import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .calibration import calculate_calibration
from .attribution import attribute_changes
from .comparison import compare_recomputed, compatibility_reasons, recompute
from .consensus import aggregate_consensus, consensus_compatibility_reasons
from .coverage import calculate_criterion_coverage
from .evaluator import evaluate
from .hashing import canonical_hash
from .models import (
    AuditEvent,
    AlternativeComparison,
    CalibrationBin,
    CalibrationDossier,
    CalibrationDossierCreate,
    CalibrationEvaluation,
    ConsensusAlternative,
    ConsensusDossier,
    ConsensusDossierCreate,
    CriterionCoverageDossier,
    CriterionCoverageDossierCreate,
    CriterionCoverageSummary,
    DecisionCreate,
    DecisionComparison,
    DecisionComparisonCreate,
    DecisionSnapshot,
    DecisionChangeAttributionDossier,
    DecisionChangeAttributionDossierCreate,
    DecisionChangeAttributionTransition,
    DecisionStabilityDossier,
    DecisionStabilityDossierCreate,
    DecisionStabilityPoint,
    DecisionStabilityTransition,
    Evaluation,
    EvaluationCriterionCoverage,
    EvaluationCreate,
    RankedAlternative,
    RecomputedEvaluationSnapshot,
    SensitivityAnalysis,
    SensitivityAnalysisCreate,
    SensitivityScenario,
)
from .sensitivity import analyze_sensitivity
from .stability import calculate_decision_stability, stability_compatibility_reasons


SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS decision_snapshots (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    specification_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL REFERENCES decision_snapshots(id),
    method TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('RECOMMENDED','BLOCKED','INSUFFICIENT')),
    recommended_alternative_key TEXT,
    ranking_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    decision_hash TEXT NOT NULL,
    outcome_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    UNIQUE(decision_id, method)
);
CREATE TABLE IF NOT EXISTS sensitivity_analyses (
    id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    decision_id TEXT NOT NULL REFERENCES decision_snapshots(id),
    method TEXT NOT NULL,
    policy TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('ROBUST','FRAGILE','INSUFFICIENT')),
    baseline_winner_alternative_key TEXT,
    winner_stability REAL NOT NULL,
    minimum_winner_margin REAL,
    scenarios_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    evaluation_hash TEXT NOT NULL,
    analysis_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    UNIQUE(evaluation_id, method, policy)
);
CREATE TABLE IF NOT EXISTS decision_comparisons (
    id TEXT PRIMARY KEY,
    baseline_evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    candidate_evaluation_id TEXT NOT NULL REFERENCES evaluations(id),
    method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('CONSISTENT','CHANGED','INCOMPATIBLE','INSUFFICIENT')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    baseline_json TEXT NOT NULL,
    candidate_json TEXT NOT NULL,
    recommendation_changed INTEGER NOT NULL CHECK(recommendation_changed IN (0,1)),
    status_changed INTEGER NOT NULL CHECK(status_changed IN (0,1)),
    ranking_changed INTEGER NOT NULL CHECK(ranking_changed IN (0,1)),
    winner_margin_change REAL,
    alternatives_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    comparison_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    UNIQUE(baseline_evaluation_id, candidate_evaluation_id, method)
);
CREATE TABLE IF NOT EXISTS consensus_dossiers (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    evaluation_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('CONSENSUS','STABLE_MAJORITY','DIVIDED','INSUFFICIENT','INCOMPATIBLE')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    evaluation_count INTEGER NOT NULL CHECK(evaluation_count BETWEEN 3 AND 50),
    sufficient_evaluation_count INTEGER NOT NULL,
    majority_alternative_key TEXT,
    majority_share REAL NOT NULL,
    evaluations_json TEXT NOT NULL,
    alternatives_json TEXT NOT NULL,
    minimum_winner_margin REAL,
    explanations_json TEXT NOT NULL,
    dossier_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calibration_dossiers (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    evaluation_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('CALIBRATED','MISALIGNED','INSUFFICIENT','INCOMPATIBLE')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    evaluation_count INTEGER NOT NULL CHECK(evaluation_count BETWEEN 3 AND 500),
    usable_evaluation_count INTEGER NOT NULL,
    coverage REAL NOT NULL,
    brier_score REAL,
    bounded_log_loss REAL,
    expected_calibration_error REAL,
    resolution REAL,
    worst_bin_index INTEGER,
    evaluations_json TEXT NOT NULL,
    bins_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    dossier_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_stability_dossiers (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    evaluation_ids_json TEXT NOT NULL,
    chronological_evaluation_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('STABLE','DRIFTING','INSUFFICIENT','INCOMPATIBLE')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    evaluation_count INTEGER NOT NULL CHECK(evaluation_count BETWEEN 2 AND 100),
    transition_count INTEGER NOT NULL,
    status_transition_count INTEGER NOT NULL,
    recommendation_transition_count INTEGER NOT NULL,
    ranking_transition_count INTEGER NOT NULL,
    churn_rate REAL NOT NULL,
    longest_status_streak INTEGER NOT NULL,
    longest_recommendation_streak INTEGER NOT NULL,
    longest_unchanged_streak INTEGER NOT NULL,
    first_recommendation TEXT,
    last_recommendation TEXT,
    worst_coverage REAL NOT NULL,
    worst_winner_margin REAL,
    evaluations_json TEXT NOT NULL,
    transitions_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    dossier_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decision_change_attribution_dossiers (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    evaluation_ids_json TEXT NOT NULL,
    chronological_evaluation_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('EXPLAINED','PARTIAL','INSUFFICIENT','INCOMPATIBLE')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    evaluation_count INTEGER NOT NULL CHECK(evaluation_count BETWEEN 2 AND 100),
    transition_count INTEGER NOT NULL,
    changed_transition_count INTEGER NOT NULL,
    explained_change_count INTEGER NOT NULL,
    unexplained_change_count INTEGER NOT NULL,
    dominant_criteria_json TEXT NOT NULL,
    winning_alternatives_json TEXT NOT NULL,
    losing_alternatives_json TEXT NOT NULL,
    worst_transition_json TEXT,
    evaluations_json TEXT NOT NULL,
    transitions_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    dossier_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS criterion_coverage_dossiers (
    id TEXT PRIMARY KEY,
    input_hash TEXT NOT NULL UNIQUE,
    evaluation_ids_json TEXT NOT NULL,
    chronological_evaluation_ids_json TEXT NOT NULL,
    method TEXT NOT NULL,
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK(qualification IN ('COMPLETE','PARTIAL','INSUFFICIENT','INCOMPATIBLE')),
    compatible INTEGER NOT NULL CHECK(compatible IN (0,1)),
    evaluation_count INTEGER NOT NULL CHECK(evaluation_count BETWEEN 2 AND 100),
    criterion_count INTEGER NOT NULL,
    required_criterion_count INTEGER NOT NULL,
    common_covered_criterion_keys_json TEXT NOT NULL,
    gap_criterion_keys_json TEXT NOT NULL,
    minimum_overall_coverage REAL NOT NULL,
    average_overall_coverage REAL NOT NULL,
    worst_evaluation_json TEXT,
    evaluations_json TEXT NOT NULL,
    criteria_json TEXT NOT NULL,
    explanations_json TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    dossier_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS decision_snapshots_no_update
BEFORE UPDATE ON decision_snapshots BEGIN SELECT RAISE(ABORT, 'immutable decision snapshot'); END;
CREATE TRIGGER IF NOT EXISTS decision_snapshots_no_delete
BEFORE DELETE ON decision_snapshots BEGIN SELECT RAISE(ABORT, 'immutable decision snapshot'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_no_update
BEFORE UPDATE ON evaluations BEGIN SELECT RAISE(ABORT, 'immutable evaluation'); END;
CREATE TRIGGER IF NOT EXISTS evaluations_no_delete
BEFORE DELETE ON evaluations BEGIN SELECT RAISE(ABORT, 'immutable evaluation'); END;
CREATE TRIGGER IF NOT EXISTS sensitivity_analyses_no_update
BEFORE UPDATE ON sensitivity_analyses BEGIN SELECT RAISE(ABORT, 'immutable sensitivity analysis'); END;
CREATE TRIGGER IF NOT EXISTS sensitivity_analyses_no_delete
BEFORE DELETE ON sensitivity_analyses BEGIN SELECT RAISE(ABORT, 'immutable sensitivity analysis'); END;
CREATE TRIGGER IF NOT EXISTS decision_comparisons_no_update
BEFORE UPDATE ON decision_comparisons BEGIN SELECT RAISE(ABORT, 'immutable decision comparison'); END;
CREATE TRIGGER IF NOT EXISTS decision_comparisons_no_delete
BEFORE DELETE ON decision_comparisons BEGIN SELECT RAISE(ABORT, 'immutable decision comparison'); END;
CREATE TRIGGER IF NOT EXISTS consensus_dossiers_no_update
BEFORE UPDATE ON consensus_dossiers BEGIN SELECT RAISE(ABORT, 'immutable consensus dossier'); END;
CREATE TRIGGER IF NOT EXISTS consensus_dossiers_no_delete
BEFORE DELETE ON consensus_dossiers BEGIN SELECT RAISE(ABORT, 'immutable consensus dossier'); END;
CREATE TRIGGER IF NOT EXISTS calibration_dossiers_no_update
BEFORE UPDATE ON calibration_dossiers BEGIN SELECT RAISE(ABORT, 'immutable calibration dossier'); END;
CREATE TRIGGER IF NOT EXISTS calibration_dossiers_no_delete
BEFORE DELETE ON calibration_dossiers BEGIN SELECT RAISE(ABORT, 'immutable calibration dossier'); END;
CREATE TRIGGER IF NOT EXISTS decision_stability_dossiers_no_update
BEFORE UPDATE ON decision_stability_dossiers BEGIN SELECT RAISE(ABORT, 'immutable decision stability dossier'); END;
CREATE TRIGGER IF NOT EXISTS decision_stability_dossiers_no_delete
BEFORE DELETE ON decision_stability_dossiers BEGIN SELECT RAISE(ABORT, 'immutable decision stability dossier'); END;
CREATE TRIGGER IF NOT EXISTS decision_change_attribution_dossiers_no_update
BEFORE UPDATE ON decision_change_attribution_dossiers BEGIN SELECT RAISE(ABORT, 'immutable decision change attribution dossier'); END;
CREATE TRIGGER IF NOT EXISTS decision_change_attribution_dossiers_no_delete
BEFORE DELETE ON decision_change_attribution_dossiers BEGIN SELECT RAISE(ABORT, 'immutable decision change attribution dossier'); END;
CREATE TRIGGER IF NOT EXISTS criterion_coverage_dossiers_no_update
BEFORE UPDATE ON criterion_coverage_dossiers BEGIN SELECT RAISE(ABORT, 'immutable criterion coverage dossier'); END;
CREATE TRIGGER IF NOT EXISTS criterion_coverage_dossiers_no_delete
BEFORE DELETE ON criterion_coverage_dossiers BEGIN SELECT RAISE(ABORT, 'immutable criterion coverage dossier'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'append-only audit log'); END;
CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'append-only audit log'); END;
"""

COMPARISON_METHOD = "decision-comparison-v1"
CONSENSUS_METHOD = "evaluation-consensus-v1"
CALIBRATION_METHOD = "decision-calibration-v1"
STABILITY_METHOD = "decision-stability-timeline-v1"
ATTRIBUTION_METHOD = "decision-change-attribution-v1"
COVERAGE_METHOD = "criterion-coverage-dossier-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Repository:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(SQLITE_SCHEMA)

    def health(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

    def _audit(self, connection, event_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
        connection.execute(
            "INSERT INTO audit_events(event_type,entity_type,entity_id,payload_json,created_at) VALUES(?,?,?,?,?)",
            (event_type, entity_type, entity_id, json.dumps(payload, ensure_ascii=False, sort_keys=True), utc_now()),
        )

    def create_decision(self, specification: DecisionCreate) -> DecisionSnapshot:
        payload = specification.model_dump(mode="json")
        input_hash = canonical_hash(payload)
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM decision_snapshots WHERE input_hash = ?", (input_hash,)
            ).fetchone()
            if existing:
                return self._decision(existing)
            decision_id = str(uuid.uuid4())
            created_at = utc_now()
            connection.execute(
                "INSERT INTO decision_snapshots(id,input_hash,specification_json,created_at) VALUES(?,?,?,?)",
                (decision_id, input_hash, specification.model_dump_json(), created_at),
            )
            self._audit(
                connection,
                "DECISION_SNAPSHOT_FROZEN",
                "decision",
                decision_id,
                {"input_hash": input_hash},
            )
        return DecisionSnapshot(
            id=decision_id,
            input_hash=input_hash,
            specification=specification,
            created_at=created_at,
        )

    def _decision(self, row) -> DecisionSnapshot:
        return DecisionSnapshot(
            id=row["id"],
            input_hash=row["input_hash"],
            specification=DecisionCreate.model_validate_json(row["specification_json"]),
            created_at=row["created_at"],
        )

    def get_decision(self, decision_id: str) -> DecisionSnapshot:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM decision_snapshots WHERE id = ?", (decision_id,)).fetchone()
        if row is None:
            raise KeyError("decision not found")
        return self._decision(row)

    def list_decisions(self) -> list[DecisionSnapshot]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM decision_snapshots ORDER BY created_at DESC, id").fetchall()
        return [self._decision(row) for row in rows]

    def evaluate_decision(self, request: EvaluationCreate) -> Evaluation:
        with self.connect() as connection:
            decision_row = connection.execute(
                "SELECT * FROM decision_snapshots WHERE id = ?", (request.decision_id,)
            ).fetchone()
            if decision_row is None:
                raise KeyError("decision not found")
            existing = connection.execute(
                "SELECT * FROM evaluations WHERE decision_id = ? AND method = ?",
                (request.decision_id, request.method),
            ).fetchone()
        if existing:
            return self._evaluation(existing, idempotent_replay=True)

        specification = DecisionCreate.model_validate_json(decision_row["specification_json"])
        status, recommended, ranking, explanations, result_hash = evaluate(specification)
        outcome_hash = canonical_hash({"decision_hash": decision_row["input_hash"], "result_hash": result_hash})
        evaluation_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO evaluations(
                    id,decision_id,method,status,recommended_alternative_key,ranking_json,
                    explanations_json,decision_hash,outcome_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    evaluation_id,
                    request.decision_id,
                    request.method,
                    status,
                    recommended,
                    json.dumps([item.model_dump(mode="json") for item in ranking], ensure_ascii=False, sort_keys=True),
                    json.dumps(explanations, ensure_ascii=False),
                    decision_row["input_hash"],
                    outcome_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "DECISION_EVALUATED",
                "evaluation",
                evaluation_id,
                {"status": status, "outcome_hash": outcome_hash},
            )
            row = connection.execute("SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)).fetchone()
        return self._evaluation(row)

    def _evaluation(self, row, idempotent_replay: bool = False) -> Evaluation:
        return Evaluation(
            id=row["id"],
            decision_id=row["decision_id"],
            method=row["method"],
            status=row["status"],
            recommended_alternative_key=row["recommended_alternative_key"],
            ranking=[RankedAlternative.model_validate(item) for item in json.loads(row["ranking_json"])],
            explanations=json.loads(row["explanations_json"]),
            decision_hash=row["decision_hash"],
            outcome_hash=row["outcome_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_evaluation(self, evaluation_id: str) -> Evaluation:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)).fetchone()
        if row is None:
            raise KeyError("evaluation not found")
        return self._evaluation(row)

    def analyze_evaluation(self, request: SensitivityAnalysisCreate) -> SensitivityAnalysis:
        with self.connect() as connection:
            evaluation_row = connection.execute(
                "SELECT * FROM evaluations WHERE id = ?", (request.evaluation_id,)
            ).fetchone()
            if evaluation_row is None:
                raise KeyError("evaluation not found")
            existing = connection.execute(
                """SELECT * FROM sensitivity_analyses
                   WHERE evaluation_id = ? AND method = ? AND policy = ?""",
                (request.evaluation_id, request.method, request.policy),
            ).fetchone()
            decision_row = connection.execute(
                "SELECT * FROM decision_snapshots WHERE id = ?", (evaluation_row["decision_id"],)
            ).fetchone()
        if existing:
            return self._sensitivity_analysis(existing, idempotent_replay=True)

        specification = DecisionCreate.model_validate_json(decision_row["specification_json"])
        qualification, baseline_winner, stability, minimum_margin, scenarios, reasons = analyze_sensitivity(
            specification
        )
        analysis_payload = {
            "evaluation_hash": evaluation_row["outcome_hash"],
            "method": request.method,
            "policy": request.policy,
            "qualification": qualification,
            "baseline_winner_alternative_key": baseline_winner,
            "winner_stability": stability,
            "minimum_winner_margin": minimum_margin,
            "scenarios": [scenario.model_dump(mode="json") for scenario in scenarios],
            "reasons": reasons,
        }
        analysis_hash = canonical_hash(analysis_payload)
        analysis_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO sensitivity_analyses(
                    id,evaluation_id,decision_id,method,policy,qualification,
                    baseline_winner_alternative_key,winner_stability,minimum_winner_margin,
                    scenarios_json,reasons_json,evaluation_hash,analysis_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    analysis_id,
                    request.evaluation_id,
                    evaluation_row["decision_id"],
                    request.method,
                    request.policy,
                    qualification,
                    baseline_winner,
                    stability,
                    minimum_margin,
                    json.dumps(
                        [scenario.model_dump(mode="json") for scenario in scenarios],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(reasons, ensure_ascii=False),
                    evaluation_row["outcome_hash"],
                    analysis_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "SENSITIVITY_ANALYSIS_FROZEN",
                "sensitivity_analysis",
                analysis_id,
                {
                    "qualification": qualification,
                    "policy": request.policy,
                    "analysis_hash": analysis_hash,
                },
            )
            row = connection.execute(
                "SELECT * FROM sensitivity_analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        return self._sensitivity_analysis(row)

    def _sensitivity_analysis(self, row, idempotent_replay: bool = False) -> SensitivityAnalysis:
        return SensitivityAnalysis(
            id=row["id"],
            evaluation_id=row["evaluation_id"],
            decision_id=row["decision_id"],
            method=row["method"],
            policy=row["policy"],
            qualification=row["qualification"],
            baseline_winner_alternative_key=row["baseline_winner_alternative_key"],
            winner_stability=row["winner_stability"],
            minimum_winner_margin=row["minimum_winner_margin"],
            scenarios=[SensitivityScenario.model_validate(item) for item in json.loads(row["scenarios_json"])],
            reasons=json.loads(row["reasons_json"]),
            evaluation_hash=row["evaluation_hash"],
            analysis_hash=row["analysis_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_sensitivity_analysis(self, analysis_id: str) -> SensitivityAnalysis:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM sensitivity_analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            raise KeyError("sensitivity analysis not found")
        return self._sensitivity_analysis(row)

    def compare_evaluations(self, request: DecisionComparisonCreate) -> DecisionComparison:
        with self.connect() as connection:
            baseline_row = connection.execute(
                "SELECT * FROM evaluations WHERE id = ?", (request.baseline_evaluation_id,)
            ).fetchone()
            candidate_row = connection.execute(
                "SELECT * FROM evaluations WHERE id = ?", (request.candidate_evaluation_id,)
            ).fetchone()
            if baseline_row is None:
                raise KeyError("baseline evaluation not found")
            if candidate_row is None:
                raise KeyError("candidate evaluation not found")
            existing = connection.execute(
                """SELECT * FROM decision_comparisons
                   WHERE baseline_evaluation_id = ? AND candidate_evaluation_id = ? AND method = ?""",
                (
                    request.baseline_evaluation_id,
                    request.candidate_evaluation_id,
                    COMPARISON_METHOD,
                ),
            ).fetchone()
            baseline_decision_row = connection.execute(
                "SELECT * FROM decision_snapshots WHERE id = ?", (baseline_row["decision_id"],)
            ).fetchone()
            candidate_decision_row = connection.execute(
                "SELECT * FROM decision_snapshots WHERE id = ?", (candidate_row["decision_id"],)
            ).fetchone()
        if existing:
            return self._decision_comparison(existing, idempotent_replay=True)

        baseline_specification = DecisionCreate.model_validate_json(
            baseline_decision_row["specification_json"]
        )
        candidate_specification = DecisionCreate.model_validate_json(
            candidate_decision_row["specification_json"]
        )
        baseline = recompute(
            evaluation_id=baseline_row["id"],
            decision_id=baseline_row["decision_id"],
            evaluation_method=baseline_row["method"],
            decision_hash=baseline_decision_row["input_hash"],
            specification=baseline_specification,
        )
        candidate = recompute(
            evaluation_id=candidate_row["id"],
            decision_id=candidate_row["decision_id"],
            evaluation_method=candidate_row["method"],
            decision_hash=candidate_decision_row["input_hash"],
            specification=candidate_specification,
        )
        if baseline.snapshot.recomputed_outcome_hash != baseline_row["outcome_hash"]:
            raise ValueError("baseline stored evaluation does not match its immutable observations")
        if candidate.snapshot.recomputed_outcome_hash != candidate_row["outcome_hash"]:
            raise ValueError("candidate stored evaluation does not match its immutable observations")

        compatibility = compatibility_reasons(
            baseline_specification,
            candidate_specification,
            baseline_row["method"],
            candidate_row["method"],
        )
        (
            qualification,
            recommendation_changed,
            status_changed,
            ranking_changed,
            margin_change,
            alternatives,
            explanations,
        ) = compare_recomputed(baseline, candidate, compatibility)
        comparison_payload = {
            "baseline": baseline.snapshot.model_dump(mode="json"),
            "candidate": candidate.snapshot.model_dump(mode="json"),
            "method": COMPARISON_METHOD,
            "qualification": qualification,
            "compatible": not compatibility,
            "recommendation_changed": recommendation_changed,
            "status_changed": status_changed,
            "ranking_changed": ranking_changed,
            "winner_margin_change": margin_change,
            "alternatives": [item.model_dump(mode="json") for item in alternatives],
            "explanations": explanations,
        }
        comparison_hash = canonical_hash(comparison_payload)
        comparison_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO decision_comparisons(
                    id,baseline_evaluation_id,candidate_evaluation_id,method,qualification,compatible,
                    baseline_json,candidate_json,recommendation_changed,status_changed,ranking_changed,
                    winner_margin_change,alternatives_json,explanations_json,comparison_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    comparison_id,
                    request.baseline_evaluation_id,
                    request.candidate_evaluation_id,
                    COMPARISON_METHOD,
                    qualification,
                    int(not compatibility),
                    baseline.snapshot.model_dump_json(),
                    candidate.snapshot.model_dump_json(),
                    int(recommendation_changed),
                    int(status_changed),
                    int(ranking_changed),
                    margin_change,
                    json.dumps(
                        [item.model_dump(mode="json") for item in alternatives],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(explanations, ensure_ascii=False),
                    comparison_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "DECISION_COMPARISON_FROZEN",
                "decision_comparison",
                comparison_id,
                {"qualification": qualification, "comparison_hash": comparison_hash},
            )
            row = connection.execute(
                "SELECT * FROM decision_comparisons WHERE id = ?", (comparison_id,)
            ).fetchone()
        return self._decision_comparison(row)

    def _decision_comparison(
        self, row, idempotent_replay: bool = False
    ) -> DecisionComparison:
        return DecisionComparison(
            id=row["id"],
            baseline_evaluation_id=row["baseline_evaluation_id"],
            candidate_evaluation_id=row["candidate_evaluation_id"],
            method=row["method"],
            qualification=row["qualification"],
            compatible=bool(row["compatible"]),
            baseline=RecomputedEvaluationSnapshot.model_validate_json(row["baseline_json"]),
            candidate=RecomputedEvaluationSnapshot.model_validate_json(row["candidate_json"]),
            recommendation_changed=bool(row["recommendation_changed"]),
            status_changed=bool(row["status_changed"]),
            ranking_changed=bool(row["ranking_changed"]),
            winner_margin_change=row["winner_margin_change"],
            alternatives=[
                AlternativeComparison.model_validate(item)
                for item in json.loads(row["alternatives_json"])
            ],
            explanations=json.loads(row["explanations_json"]),
            comparison_hash=row["comparison_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_decision_comparison(self, comparison_id: str) -> DecisionComparison:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM decision_comparisons WHERE id = ?", (comparison_id,)
            ).fetchone()
        if row is None:
            raise KeyError("decision comparison not found")
        return self._decision_comparison(row)

    def create_consensus_dossier(self, request: ConsensusDossierCreate) -> ConsensusDossier:
        evaluation_ids = sorted(request.evaluation_ids)
        input_hash = canonical_hash({"evaluation_ids": evaluation_ids})
        evaluation_rows = []
        decision_rows = []
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM consensus_dossiers WHERE input_hash = ?", (input_hash,)
            ).fetchone()
            if existing:
                return self._consensus_dossier(existing, idempotent_replay=True)
            for evaluation_id in evaluation_ids:
                evaluation_row = connection.execute(
                    "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
                ).fetchone()
                if evaluation_row is None:
                    raise KeyError(f"evaluation not found: {evaluation_id}")
                decision_row = connection.execute(
                    "SELECT * FROM decision_snapshots WHERE id = ?",
                    (evaluation_row["decision_id"],),
                ).fetchone()
                evaluation_rows.append(evaluation_row)
                decision_rows.append(decision_row)

        specifications = [
            DecisionCreate.model_validate_json(row["specification_json"]) for row in decision_rows
        ]
        recomputed = []
        for evaluation_row, decision_row, specification in zip(
            evaluation_rows, decision_rows, specifications
        ):
            result = recompute(
                evaluation_id=evaluation_row["id"],
                decision_id=evaluation_row["decision_id"],
                evaluation_method=evaluation_row["method"],
                decision_hash=decision_row["input_hash"],
                specification=specification,
            )
            if result.snapshot.recomputed_outcome_hash != evaluation_row["outcome_hash"]:
                raise ValueError(
                    f"stored evaluation {evaluation_row['id']} does not match its immutable observations"
                )
            recomputed.append(result)

        evaluation_methods = [row["method"] for row in evaluation_rows]
        compatibility = consensus_compatibility_reasons(specifications, evaluation_methods)
        (
            qualification,
            sufficient_count,
            majority_key,
            majority_share,
            alternatives,
            minimum_margin,
            explanations,
        ) = aggregate_consensus(recomputed, compatibility)
        evaluation_method = evaluation_methods[0] if len(set(evaluation_methods)) == 1 else "mixed"
        dossier_payload = {
            "input_hash": input_hash,
            "evaluation_ids": evaluation_ids,
            "method": CONSENSUS_METHOD,
            "evaluation_method": evaluation_method,
            "qualification": qualification,
            "compatible": not compatibility,
            "evaluation_count": len(evaluation_ids),
            "sufficient_evaluation_count": sufficient_count,
            "majority_alternative_key": majority_key,
            "majority_share": majority_share,
            "evaluations": [item.snapshot.model_dump(mode="json") for item in recomputed],
            "alternatives": [item.model_dump(mode="json") for item in alternatives],
            "minimum_winner_margin": minimum_margin,
            "explanations": explanations,
        }
        dossier_hash = canonical_hash(dossier_payload)
        dossier_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO consensus_dossiers(
                    id,input_hash,evaluation_ids_json,method,evaluation_method,qualification,compatible,
                    evaluation_count,sufficient_evaluation_count,majority_alternative_key,majority_share,
                    evaluations_json,alternatives_json,minimum_winner_margin,explanations_json,
                    dossier_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    input_hash,
                    json.dumps(evaluation_ids),
                    CONSENSUS_METHOD,
                    evaluation_method,
                    qualification,
                    int(not compatibility),
                    len(evaluation_ids),
                    sufficient_count,
                    majority_key,
                    majority_share,
                    json.dumps(
                        [item.snapshot.model_dump(mode="json") for item in recomputed],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in alternatives],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    minimum_margin,
                    json.dumps(explanations, ensure_ascii=False),
                    dossier_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "CONSENSUS_DOSSIER_FROZEN",
                "consensus_dossier",
                dossier_id,
                {"qualification": qualification, "dossier_hash": dossier_hash},
            )
            row = connection.execute(
                "SELECT * FROM consensus_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        return self._consensus_dossier(row)

    def _consensus_dossier(self, row, idempotent_replay: bool = False) -> ConsensusDossier:
        return ConsensusDossier(
            id=row["id"],
            evaluation_ids=json.loads(row["evaluation_ids_json"]),
            method=row["method"],
            evaluation_method=row["evaluation_method"],
            qualification=row["qualification"],
            compatible=bool(row["compatible"]),
            evaluation_count=row["evaluation_count"],
            sufficient_evaluation_count=row["sufficient_evaluation_count"],
            majority_alternative_key=row["majority_alternative_key"],
            majority_share=row["majority_share"],
            evaluations=[
                RecomputedEvaluationSnapshot.model_validate(item)
                for item in json.loads(row["evaluations_json"])
            ],
            alternatives=[
                ConsensusAlternative.model_validate(item)
                for item in json.loads(row["alternatives_json"])
            ],
            minimum_winner_margin=row["minimum_winner_margin"],
            explanations=json.loads(row["explanations_json"]),
            input_hash=row["input_hash"],
            dossier_hash=row["dossier_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_consensus_dossier(self, dossier_id: str) -> ConsensusDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM consensus_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        if row is None:
            raise KeyError("consensus dossier not found")
        return self._consensus_dossier(row)

    def create_calibration_dossier(
        self, request: CalibrationDossierCreate
    ) -> CalibrationDossier:
        evaluation_ids = sorted(request.evaluation_ids)
        input_hash = canonical_hash({"evaluation_ids": evaluation_ids})
        evaluation_rows = []
        decision_rows = []
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM calibration_dossiers WHERE input_hash = ?", (input_hash,)
            ).fetchone()
            if existing:
                return self._calibration_dossier(existing, idempotent_replay=True)
            for evaluation_id in evaluation_ids:
                evaluation_row = connection.execute(
                    "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
                ).fetchone()
                if evaluation_row is None:
                    raise KeyError(f"evaluation not found: {evaluation_id}")
                decision_row = connection.execute(
                    "SELECT * FROM decision_snapshots WHERE id = ?",
                    (evaluation_row["decision_id"],),
                ).fetchone()
                evaluation_rows.append(evaluation_row)
                decision_rows.append(decision_row)

        specifications = [
            DecisionCreate.model_validate_json(row["specification_json"]) for row in decision_rows
        ]
        recomputed = []
        for evaluation_row, decision_row, specification in zip(
            evaluation_rows, decision_rows, specifications
        ):
            result = recompute(
                evaluation_id=evaluation_row["id"],
                decision_id=evaluation_row["decision_id"],
                evaluation_method=evaluation_row["method"],
                decision_hash=decision_row["input_hash"],
                specification=specification,
            )
            if result.snapshot.recomputed_outcome_hash != evaluation_row["outcome_hash"]:
                raise ValueError(
                    f"stored evaluation {evaluation_row['id']} does not match its immutable observations"
                )
            recomputed.append(result)

        compatibility = consensus_compatibility_reasons(
            specifications, [row["method"] for row in evaluation_rows]
        )
        (
            qualification,
            calibration_evaluations,
            bins,
            coverage,
            brier_score,
            bounded_log_loss,
            expected_calibration_error,
            resolution,
            worst_bin_index,
            explanations,
        ) = calculate_calibration(specifications, recomputed, compatibility)
        dossier_payload = {
            "input_hash": input_hash,
            "evaluation_ids": evaluation_ids,
            "method": CALIBRATION_METHOD,
            "qualification": qualification,
            "compatible": not compatibility,
            "evaluation_count": len(evaluation_ids),
            "usable_evaluation_count": len(calibration_evaluations),
            "coverage": coverage,
            "brier_score": brier_score,
            "bounded_log_loss": bounded_log_loss,
            "expected_calibration_error": expected_calibration_error,
            "resolution": resolution,
            "worst_bin_index": worst_bin_index,
            "evaluations": [item.model_dump(mode="json") for item in calibration_evaluations],
            "bins": [item.model_dump(mode="json") for item in bins],
            "explanations": explanations,
        }
        dossier_hash = canonical_hash(dossier_payload)
        dossier_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO calibration_dossiers(
                    id,input_hash,evaluation_ids_json,method,qualification,compatible,
                    evaluation_count,usable_evaluation_count,coverage,brier_score,bounded_log_loss,
                    expected_calibration_error,resolution,worst_bin_index,evaluations_json,bins_json,
                    explanations_json,dossier_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    input_hash,
                    json.dumps(evaluation_ids),
                    CALIBRATION_METHOD,
                    qualification,
                    int(not compatibility),
                    len(evaluation_ids),
                    len(calibration_evaluations),
                    coverage,
                    brier_score,
                    bounded_log_loss,
                    expected_calibration_error,
                    resolution,
                    worst_bin_index,
                    json.dumps(
                        [item.model_dump(mode="json") for item in calibration_evaluations],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(
                        [item.model_dump(mode="json") for item in bins],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    json.dumps(explanations, ensure_ascii=False),
                    dossier_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "CALIBRATION_DOSSIER_FROZEN",
                "calibration_dossier",
                dossier_id,
                {"qualification": qualification, "dossier_hash": dossier_hash},
            )
            row = connection.execute(
                "SELECT * FROM calibration_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        return self._calibration_dossier(row)

    def _calibration_dossier(
        self, row, idempotent_replay: bool = False
    ) -> CalibrationDossier:
        return CalibrationDossier(
            id=row["id"],
            evaluation_ids=json.loads(row["evaluation_ids_json"]),
            method=row["method"],
            qualification=row["qualification"],
            compatible=bool(row["compatible"]),
            evaluation_count=row["evaluation_count"],
            usable_evaluation_count=row["usable_evaluation_count"],
            coverage=row["coverage"],
            brier_score=row["brier_score"],
            bounded_log_loss=row["bounded_log_loss"],
            expected_calibration_error=row["expected_calibration_error"],
            resolution=row["resolution"],
            worst_bin_index=row["worst_bin_index"],
            evaluations=[
                CalibrationEvaluation.model_validate(item)
                for item in json.loads(row["evaluations_json"])
            ],
            bins=[CalibrationBin.model_validate(item) for item in json.loads(row["bins_json"])],
            explanations=json.loads(row["explanations_json"]),
            input_hash=row["input_hash"],
            dossier_hash=row["dossier_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_calibration_dossier(self, dossier_id: str) -> CalibrationDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM calibration_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        if row is None:
            raise KeyError("calibration dossier not found")
        return self._calibration_dossier(row)

    def list_calibration_dossiers(self) -> list[CalibrationDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM calibration_dossiers ORDER BY created_at DESC, id"
            ).fetchall()
        return [self._calibration_dossier(row) for row in rows]

    def create_decision_stability_dossier(
        self, request: DecisionStabilityDossierCreate
    ) -> DecisionStabilityDossier:
        evaluation_ids = sorted(request.evaluation_ids)
        input_hash = canonical_hash({"evaluation_ids": evaluation_ids, "method": STABILITY_METHOD})
        evaluation_rows = []
        decision_rows = []
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM decision_stability_dossiers WHERE input_hash = ?", (input_hash,)
            ).fetchone()
            if existing:
                return self._decision_stability_dossier(existing, idempotent_replay=True)
            for evaluation_id in evaluation_ids:
                evaluation_row = connection.execute(
                    "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
                ).fetchone()
                if evaluation_row is None:
                    raise KeyError(f"evaluation not found: {evaluation_id}")
                decision_row = connection.execute(
                    "SELECT * FROM decision_snapshots WHERE id = ?",
                    (evaluation_row["decision_id"],),
                ).fetchone()
                evaluation_rows.append(evaluation_row)
                decision_rows.append(decision_row)

        loaded = list(zip(evaluation_rows, decision_rows))
        loaded.sort(key=lambda pair: (pair[0]["created_at"], pair[0]["id"]))
        specifications = [
            DecisionCreate.model_validate_json(decision_row["specification_json"])
            for _, decision_row in loaded
        ]
        recomputed = []
        for (evaluation_row, decision_row), specification in zip(loaded, specifications):
            if canonical_hash(specification.model_dump(mode="json")) != decision_row["input_hash"]:
                raise ValueError(
                    f"stored decision {decision_row['id']} does not match its immutable input hash"
                )
            result = recompute(
                evaluation_id=evaluation_row["id"],
                decision_id=evaluation_row["decision_id"],
                evaluation_method=evaluation_row["method"],
                decision_hash=decision_row["input_hash"],
                specification=specification,
            )
            if result.snapshot.recomputed_outcome_hash != evaluation_row["outcome_hash"]:
                raise ValueError(
                    f"stored evaluation {evaluation_row['id']} does not match its immutable observations"
                )
            recomputed.append((result, evaluation_row["created_at"]))

        methods = [evaluation_row["method"] for evaluation_row, _ in loaded]
        compatibility = stability_compatibility_reasons(specifications, methods)
        (
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
        ) = calculate_decision_stability(recomputed, compatibility)
        chronological_ids = [item.evaluation_id for item in points]
        evidence_payload = {
            "evaluations": [item.model_dump(mode="json") for item in points],
            "transitions": [item.model_dump(mode="json") for item in transitions],
        }
        evidence_hash = canonical_hash(evidence_payload)
        dossier_payload = {
            "input_hash": input_hash,
            "evaluation_ids": evaluation_ids,
            "chronological_evaluation_ids": chronological_ids,
            "method": STABILITY_METHOD,
            "evaluation_method": methods[0] if len(set(methods)) == 1 else "mixed",
            "qualification": qualification,
            "compatible": not compatibility,
            "evaluation_count": len(points),
            "transition_count": len(transitions),
            "status_transition_count": status_changes,
            "recommendation_transition_count": recommendation_changes,
            "ranking_transition_count": ranking_changes,
            "churn_rate": churn_rate,
            "longest_status_streak": longest_status,
            "longest_recommendation_streak": longest_recommendation,
            "longest_unchanged_streak": longest_unchanged,
            "first_recommendation": first_recommendation,
            "last_recommendation": last_recommendation,
            "worst_coverage": worst_coverage,
            "worst_winner_margin": worst_margin,
            "explanations": explanations,
            "evidence_hash": evidence_hash,
        }
        dossier_hash = canonical_hash(dossier_payload)
        dossier_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO decision_stability_dossiers(
                    id,input_hash,evaluation_ids_json,chronological_evaluation_ids_json,method,
                    evaluation_method,qualification,compatible,evaluation_count,transition_count,
                    status_transition_count,recommendation_transition_count,ranking_transition_count,
                    churn_rate,longest_status_streak,longest_recommendation_streak,
                    longest_unchanged_streak,first_recommendation,last_recommendation,worst_coverage,
                    worst_winner_margin,evaluations_json,transitions_json,explanations_json,
                    evidence_hash,dossier_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    input_hash,
                    json.dumps(evaluation_ids),
                    json.dumps(chronological_ids),
                    STABILITY_METHOD,
                    methods[0] if len(set(methods)) == 1 else "mixed",
                    qualification,
                    int(not compatibility),
                    len(points),
                    len(transitions),
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
                    json.dumps([item.model_dump(mode="json") for item in points], ensure_ascii=False, sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in transitions], ensure_ascii=False, sort_keys=True),
                    json.dumps(explanations, ensure_ascii=False),
                    evidence_hash,
                    dossier_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "DECISION_STABILITY_DOSSIER_FROZEN",
                "decision_stability_dossier",
                dossier_id,
                {"qualification": qualification, "dossier_hash": dossier_hash},
            )
            row = connection.execute(
                "SELECT * FROM decision_stability_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        return self._decision_stability_dossier(row)

    def _decision_stability_dossier(
        self, row, idempotent_replay: bool = False
    ) -> DecisionStabilityDossier:
        return DecisionStabilityDossier(
            id=row["id"],
            evaluation_ids=json.loads(row["evaluation_ids_json"]),
            chronological_evaluation_ids=json.loads(row["chronological_evaluation_ids_json"]),
            method=row["method"],
            evaluation_method=row["evaluation_method"],
            qualification=row["qualification"],
            compatible=bool(row["compatible"]),
            evaluation_count=row["evaluation_count"],
            transition_count=row["transition_count"],
            status_transition_count=row["status_transition_count"],
            recommendation_transition_count=row["recommendation_transition_count"],
            ranking_transition_count=row["ranking_transition_count"],
            churn_rate=row["churn_rate"],
            longest_status_streak=row["longest_status_streak"],
            longest_recommendation_streak=row["longest_recommendation_streak"],
            longest_unchanged_streak=row["longest_unchanged_streak"],
            first_recommendation=row["first_recommendation"],
            last_recommendation=row["last_recommendation"],
            worst_coverage=row["worst_coverage"],
            worst_winner_margin=row["worst_winner_margin"],
            evaluations=[DecisionStabilityPoint.model_validate(item) for item in json.loads(row["evaluations_json"])],
            transitions=[DecisionStabilityTransition.model_validate(item) for item in json.loads(row["transitions_json"])],
            explanations=json.loads(row["explanations_json"]),
            input_hash=row["input_hash"],
            evidence_hash=row["evidence_hash"],
            dossier_hash=row["dossier_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_decision_stability_dossier(self, dossier_id: str) -> DecisionStabilityDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM decision_stability_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        if row is None:
            raise KeyError("decision stability dossier not found")
        return self._decision_stability_dossier(row)

    def list_decision_stability_dossiers(self) -> list[DecisionStabilityDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decision_stability_dossiers ORDER BY created_at DESC, id"
            ).fetchall()
        return [self._decision_stability_dossier(row) for row in rows]

    def create_decision_change_attribution_dossier(
        self, request: DecisionChangeAttributionDossierCreate
    ) -> DecisionChangeAttributionDossier:
        evaluation_ids = sorted(request.evaluation_ids)
        input_hash = canonical_hash({"evaluation_ids": evaluation_ids, "method": ATTRIBUTION_METHOD})
        loaded = []
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM decision_change_attribution_dossiers WHERE input_hash = ?",
                (input_hash,),
            ).fetchone()
            if existing:
                return self._decision_change_attribution_dossier(existing, idempotent_replay=True)
            for evaluation_id in evaluation_ids:
                evaluation_row = connection.execute(
                    "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
                ).fetchone()
                if evaluation_row is None:
                    raise KeyError(f"evaluation not found: {evaluation_id}")
                decision_row = connection.execute(
                    "SELECT * FROM decision_snapshots WHERE id = ?",
                    (evaluation_row["decision_id"],),
                ).fetchone()
                loaded.append((evaluation_row, decision_row))
        loaded.sort(key=lambda pair: (pair[0]["created_at"], pair[0]["id"]))
        specifications = [
            DecisionCreate.model_validate_json(decision_row["specification_json"])
            for _, decision_row in loaded
        ]
        recomputed = []
        for (evaluation_row, decision_row), specification in zip(loaded, specifications):
            if canonical_hash(specification.model_dump(mode="json")) != decision_row["input_hash"]:
                raise ValueError(
                    f"stored decision {decision_row['id']} does not match its immutable input hash"
                )
            result = recompute(
                evaluation_id=evaluation_row["id"],
                decision_id=evaluation_row["decision_id"],
                evaluation_method=evaluation_row["method"],
                decision_hash=decision_row["input_hash"],
                specification=specification,
            )
            if result.snapshot.recomputed_outcome_hash != evaluation_row["outcome_hash"]:
                raise ValueError(
                    f"stored evaluation {evaluation_row['id']} does not match its immutable observations"
                )
            recomputed.append(result)
        methods = [evaluation_row["method"] for evaluation_row, _ in loaded]
        compatibility = stability_compatibility_reasons(specifications, methods)
        (
            qualification,
            transitions,
            changed_count,
            explained_count,
            unexplained_count,
            dominant_criteria,
            winners,
            losers,
            worst,
            explanations,
        ) = attribute_changes(recomputed, specifications, compatibility)
        chronological_ids = [item.snapshot.evaluation_id for item in recomputed]
        evaluation_snapshots = [item.snapshot for item in recomputed]
        evidence_payload = {
            "evaluation_ids": evaluation_ids,
            "chronological_evaluation_ids": chronological_ids,
            "decision_hashes": [item.snapshot.decision_hash for item in recomputed],
            "outcome_hashes": [item.snapshot.recomputed_outcome_hash for item in recomputed],
            "transitions": [item.model_dump(mode="json") for item in transitions],
        }
        evidence_hash = canonical_hash(evidence_payload)
        dossier_payload = {
            "input_hash": input_hash,
            "chronological_evaluation_ids": chronological_ids,
            "method": ATTRIBUTION_METHOD,
            "evaluation_method": methods[0] if len(set(methods)) == 1 else "mixed",
            "qualification": qualification,
            "compatible": not compatibility,
            "evaluation_count": len(recomputed),
            "transition_count": len(transitions),
            "changed_transition_count": changed_count,
            "explained_change_count": explained_count,
            "unexplained_change_count": unexplained_count,
            "dominant_criteria": dominant_criteria,
            "winning_alternatives": winners,
            "losing_alternatives": losers,
            "worst_transition": worst.model_dump(mode="json") if worst else None,
            "evaluations": [item.model_dump(mode="json") for item in evaluation_snapshots],
            "transitions": [item.model_dump(mode="json") for item in transitions],
            "explanations": explanations,
            "evidence_hash": evidence_hash,
        }
        dossier_hash = canonical_hash(dossier_payload)
        dossier_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO decision_change_attribution_dossiers(
                    id,input_hash,evaluation_ids_json,chronological_evaluation_ids_json,method,
                    evaluation_method,qualification,compatible,evaluation_count,transition_count,
                    changed_transition_count,explained_change_count,unexplained_change_count,
                    dominant_criteria_json,winning_alternatives_json,losing_alternatives_json,
                    worst_transition_json,evaluations_json,transitions_json,explanations_json,
                    evidence_hash,dossier_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,
                    input_hash,
                    json.dumps(evaluation_ids),
                    json.dumps(chronological_ids),
                    ATTRIBUTION_METHOD,
                    methods[0] if len(set(methods)) == 1 else "mixed",
                    qualification,
                    int(not compatibility),
                    len(recomputed),
                    len(transitions),
                    changed_count,
                    explained_count,
                    unexplained_count,
                    json.dumps(dominant_criteria),
                    json.dumps(winners),
                    json.dumps(losers),
                    worst.model_dump_json() if worst else None,
                    json.dumps([item.model_dump(mode="json") for item in evaluation_snapshots], ensure_ascii=False, sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in transitions], ensure_ascii=False, sort_keys=True),
                    json.dumps(explanations, ensure_ascii=False),
                    evidence_hash,
                    dossier_hash,
                    created_at,
                ),
            )
            self._audit(
                connection,
                "DECISION_CHANGE_ATTRIBUTION_DOSSIER_FROZEN",
                "decision_change_attribution_dossier",
                dossier_id,
                {"qualification": qualification, "dossier_hash": dossier_hash},
            )
            row = connection.execute(
                "SELECT * FROM decision_change_attribution_dossiers WHERE id = ?",
                (dossier_id,),
            ).fetchone()
        return self._decision_change_attribution_dossier(row)

    def _decision_change_attribution_dossier(
        self, row, idempotent_replay: bool = False
    ) -> DecisionChangeAttributionDossier:
        raw_worst = row["worst_transition_json"]
        return DecisionChangeAttributionDossier(
            id=row["id"],
            evaluation_ids=json.loads(row["evaluation_ids_json"]),
            chronological_evaluation_ids=json.loads(row["chronological_evaluation_ids_json"]),
            method=row["method"],
            evaluation_method=row["evaluation_method"],
            qualification=row["qualification"],
            compatible=bool(row["compatible"]),
            evaluation_count=row["evaluation_count"],
            transition_count=row["transition_count"],
            changed_transition_count=row["changed_transition_count"],
            explained_change_count=row["explained_change_count"],
            unexplained_change_count=row["unexplained_change_count"],
            dominant_criteria=json.loads(row["dominant_criteria_json"]),
            winning_alternatives=json.loads(row["winning_alternatives_json"]),
            losing_alternatives=json.loads(row["losing_alternatives_json"]),
            worst_transition=(
                DecisionChangeAttributionTransition.model_validate_json(raw_worst)
                if raw_worst else None
            ),
            evaluations=[
                RecomputedEvaluationSnapshot.model_validate(item)
                for item in json.loads(row["evaluations_json"])
            ],
            transitions=[
                DecisionChangeAttributionTransition.model_validate(item)
                for item in json.loads(row["transitions_json"])
            ],
            explanations=json.loads(row["explanations_json"]),
            input_hash=row["input_hash"],
            evidence_hash=row["evidence_hash"],
            dossier_hash=row["dossier_hash"],
            idempotent_replay=idempotent_replay,
            created_at=row["created_at"],
        )

    def get_decision_change_attribution_dossier(
        self, dossier_id: str
    ) -> DecisionChangeAttributionDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM decision_change_attribution_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        if row is None:
            raise KeyError("decision change attribution dossier not found")
        return self._decision_change_attribution_dossier(row)

    def list_decision_change_attribution_dossiers(
        self,
    ) -> list[DecisionChangeAttributionDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM decision_change_attribution_dossiers ORDER BY created_at DESC,id"
            ).fetchall()
        return [self._decision_change_attribution_dossier(row) for row in rows]

    def create_criterion_coverage_dossier(
        self, request: CriterionCoverageDossierCreate
    ) -> CriterionCoverageDossier:
        evaluation_ids = sorted(request.evaluation_ids)
        input_hash = canonical_hash({"evaluation_ids": evaluation_ids, "method": COVERAGE_METHOD})
        loaded = []
        with self.connect() as connection:
            existing = connection.execute(
                "SELECT * FROM criterion_coverage_dossiers WHERE input_hash = ?", (input_hash,)
            ).fetchone()
            if existing:
                return self._criterion_coverage_dossier(existing, idempotent_replay=True)
            for evaluation_id in evaluation_ids:
                evaluation_row = connection.execute(
                    "SELECT * FROM evaluations WHERE id = ?", (evaluation_id,)
                ).fetchone()
                if evaluation_row is None:
                    raise KeyError(f"evaluation not found: {evaluation_id}")
                decision_row = connection.execute(
                    "SELECT * FROM decision_snapshots WHERE id = ?", (evaluation_row["decision_id"],)
                ).fetchone()
                loaded.append((evaluation_row, decision_row))
        loaded.sort(key=lambda pair: (pair[0]["created_at"], pair[0]["id"]))
        specifications = [
            DecisionCreate.model_validate_json(decision_row["specification_json"])
            for _, decision_row in loaded
        ]
        recomputed = []
        for (evaluation_row, decision_row), specification in zip(loaded, specifications):
            if canonical_hash(specification.model_dump(mode="json")) != decision_row["input_hash"]:
                raise ValueError(
                    f"stored decision {decision_row['id']} does not match its immutable input hash"
                )
            result = recompute(
                evaluation_id=evaluation_row["id"],
                decision_id=evaluation_row["decision_id"],
                evaluation_method=evaluation_row["method"],
                decision_hash=decision_row["input_hash"],
                specification=specification,
            )
            if result.snapshot.recomputed_outcome_hash != evaluation_row["outcome_hash"]:
                raise ValueError(
                    f"stored evaluation {evaluation_row['id']} does not match its immutable observations"
                )
            recomputed.append(result)
        methods = [evaluation_row["method"] for evaluation_row, _ in loaded]
        compatibility = stability_compatibility_reasons(specifications, methods)
        (
            qualification, points, criteria, common_covered, gap_keys,
            minimum_overall, average_overall, worst, explanations,
        ) = calculate_criterion_coverage(
            recomputed,
            specifications,
            [evaluation_row["created_at"] for evaluation_row, _ in loaded],
            compatibility,
        )
        chronological_ids = [evaluation_row["id"] for evaluation_row, _ in loaded]
        evidence_payload = {
            "chronological_evaluation_ids": chronological_ids,
            "decision_hashes": [item.snapshot.decision_hash for item in recomputed],
            "outcome_hashes": [item.snapshot.recomputed_outcome_hash for item in recomputed],
            "evaluations": [item.model_dump(mode="json") for item in points],
            "criteria": [item.model_dump(mode="json") for item in criteria],
        }
        evidence_hash = canonical_hash(evidence_payload)
        required_count = sum(item.required for item in specifications[0].criteria) if not compatibility else 0
        criterion_count = len(specifications[0].criteria) if not compatibility else 0
        dossier_payload = {
            "input_hash": input_hash,
            "chronological_evaluation_ids": chronological_ids,
            "method": COVERAGE_METHOD,
            "evaluation_method": methods[0] if len(set(methods)) == 1 else "mixed",
            "qualification": qualification,
            "compatible": not compatibility,
            "evaluation_count": len(evaluation_ids),
            "criterion_count": criterion_count,
            "required_criterion_count": required_count,
            "common_covered_criterion_keys": common_covered,
            "gap_criterion_keys": gap_keys,
            "minimum_overall_coverage": minimum_overall,
            "average_overall_coverage": average_overall,
            "worst_evaluation": worst.model_dump(mode="json") if worst else None,
            "explanations": explanations,
            "evidence_hash": evidence_hash,
        }
        dossier_hash = canonical_hash(dossier_payload)
        dossier_id = str(uuid.uuid4())
        created_at = utc_now()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO criterion_coverage_dossiers(
                    id,input_hash,evaluation_ids_json,chronological_evaluation_ids_json,method,
                    evaluation_method,qualification,compatible,evaluation_count,criterion_count,
                    required_criterion_count,common_covered_criterion_keys_json,gap_criterion_keys_json,
                    minimum_overall_coverage,average_overall_coverage,worst_evaluation_json,
                    evaluations_json,criteria_json,explanations_json,evidence_hash,dossier_hash,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    dossier_id,input_hash,json.dumps(evaluation_ids),json.dumps(chronological_ids),
                    COVERAGE_METHOD,methods[0] if len(set(methods)) == 1 else "mixed",qualification,
                    int(not compatibility),len(evaluation_ids),criterion_count,required_count,
                    json.dumps(common_covered),json.dumps(gap_keys),minimum_overall,average_overall,
                    worst.model_dump_json() if worst else None,
                    json.dumps([item.model_dump(mode="json") for item in points], ensure_ascii=False, sort_keys=True),
                    json.dumps([item.model_dump(mode="json") for item in criteria], ensure_ascii=False, sort_keys=True),
                    json.dumps(explanations, ensure_ascii=False),evidence_hash,dossier_hash,created_at,
                ),
            )
            self._audit(
                connection,"CRITERION_COVERAGE_DOSSIER_FROZEN","criterion_coverage_dossier",
                dossier_id,{"qualification": qualification, "dossier_hash": dossier_hash},
            )
            row = connection.execute(
                "SELECT * FROM criterion_coverage_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        return self._criterion_coverage_dossier(row)

    def _criterion_coverage_dossier(
        self, row, idempotent_replay: bool = False
    ) -> CriterionCoverageDossier:
        return CriterionCoverageDossier(
            id=row["id"],evaluation_ids=json.loads(row["evaluation_ids_json"]),
            chronological_evaluation_ids=json.loads(row["chronological_evaluation_ids_json"]),
            method=row["method"],evaluation_method=row["evaluation_method"],
            qualification=row["qualification"],compatible=bool(row["compatible"]),
            evaluation_count=row["evaluation_count"],criterion_count=row["criterion_count"],
            required_criterion_count=row["required_criterion_count"],
            common_covered_criterion_keys=json.loads(row["common_covered_criterion_keys_json"]),
            gap_criterion_keys=json.loads(row["gap_criterion_keys_json"]),
            minimum_overall_coverage=row["minimum_overall_coverage"],
            average_overall_coverage=row["average_overall_coverage"],
            worst_evaluation=(EvaluationCriterionCoverage.model_validate_json(row["worst_evaluation_json"])
                              if row["worst_evaluation_json"] else None),
            evaluations=[EvaluationCriterionCoverage.model_validate(item) for item in json.loads(row["evaluations_json"])],
            criteria=[CriterionCoverageSummary.model_validate(item) for item in json.loads(row["criteria_json"])],
            explanations=json.loads(row["explanations_json"]),input_hash=row["input_hash"],
            evidence_hash=row["evidence_hash"],dossier_hash=row["dossier_hash"],
            idempotent_replay=idempotent_replay,created_at=row["created_at"],
        )

    def get_criterion_coverage_dossier(self, dossier_id: str) -> CriterionCoverageDossier:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM criterion_coverage_dossiers WHERE id = ?", (dossier_id,)
            ).fetchone()
        if row is None:
            raise KeyError("criterion coverage dossier not found")
        return self._criterion_coverage_dossier(row)

    def list_criterion_coverage_dossiers(self) -> list[CriterionCoverageDossier]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM criterion_coverage_dossiers ORDER BY created_at DESC,id"
            ).fetchall()
        return [self._criterion_coverage_dossier(row) for row in rows]

    def list_audit_events(self) -> list[AuditEvent]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM audit_events ORDER BY sequence").fetchall()
        return [
            AuditEvent(
                sequence=row["sequence"],
                event_type=row["event_type"],
                entity_type=row["entity_type"],
                entity_id=row["entity_id"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]
