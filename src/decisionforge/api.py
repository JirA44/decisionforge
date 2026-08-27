import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from . import __version__
from .models import (
    AuditEvent,
    CalibrationDossier,
    CalibrationDossierCreate,
    ConsensusDossier,
    ConsensusDossierCreate,
    CriterionCoverageDossier,
    CriterionCoverageDossierCreate,
    DecisionCreate,
    DecisionChangeAttributionDossier,
    DecisionChangeAttributionDossierCreate,
    DecisionComparison,
    DecisionComparisonCreate,
    DecisionSnapshot,
    DecisionStabilityDossier,
    DecisionStabilityDossierCreate,
    Evaluation,
    EvaluationCreate,
    SensitivityAnalysis,
    SensitivityAnalysisCreate,
)
from .repository import Repository


def default_database_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "decisionforge.sqlite3"


def create_app(database_path: str | Path | None = None) -> FastAPI:
    resolved_path = database_path or os.getenv("DECISIONFORGE_DB") or default_database_path()
    repository = Repository(resolved_path)
    application = FastAPI(
        title="DecisionForge API",
        version=__version__,
        description=(
            "Registre immuable de décisions, recommandations déterministes, analyses bornées "
            "de sensibilité, comparaisons, consensus, calibration et stabilité chronologique "
            "recalculés à partir des preuves persistées, avec attribution chronologique des changements."
            " La couverture des critères est également qualifiée sur des séries compatibles."
        ),
    )
    application.state.repository = repository

    @application.get("/health", tags=["system"])
    def health():
        return {"status": "ok" if repository.health() else "error", "version": __version__, "database": "ok"}

    @application.get("/info", tags=["system"])
    def info():
        return {
            "name": "DecisionForge",
            "version": __version__,
            "consensus_method": "evaluation-consensus-v1",
            "calibration_method": "decision-calibration-v1",
            "stability_method": "decision-stability-timeline-v1",
            "attribution_method": "decision-change-attribution-v1",
            "criterion_coverage_method": "criterion-coverage-dossier-v1",
            "automatic_action": False,
        }

    @application.post("/v1/decisions", response_model=DecisionSnapshot, status_code=201, tags=["decisions"])
    def create_decision(data: DecisionCreate):
        return repository.create_decision(data)

    @application.get("/v1/decisions", response_model=list[DecisionSnapshot], tags=["decisions"])
    def list_decisions():
        return repository.list_decisions()

    @application.get("/v1/decisions/{decision_id}", response_model=DecisionSnapshot, tags=["decisions"])
    def get_decision(decision_id: str):
        try:
            return repository.get_decision(decision_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/v1/evaluations", response_model=Evaluation, status_code=201, tags=["evaluations"])
    def create_evaluation(data: EvaluationCreate):
        try:
            return repository.evaluate_decision(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/v1/evaluations/{evaluation_id}", response_model=Evaluation, tags=["evaluations"])
    def get_evaluation(evaluation_id: str):
        try:
            return repository.get_evaluation(evaluation_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/sensitivity-analyses",
        response_model=SensitivityAnalysis,
        status_code=201,
        tags=["sensitivity"],
    )
    def create_sensitivity_analysis(data: SensitivityAnalysisCreate):
        try:
            return repository.analyze_evaluation(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/v1/sensitivity-analyses/{analysis_id}",
        response_model=SensitivityAnalysis,
        tags=["sensitivity"],
    )
    def get_sensitivity_analysis(analysis_id: str):
        try:
            return repository.get_sensitivity_analysis(analysis_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/decision-comparisons",
        response_model=DecisionComparison,
        status_code=201,
        tags=["comparisons"],
    )
    def create_decision_comparison(data: DecisionComparisonCreate):
        try:
            return repository.compare_evaluations(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/v1/decision-comparisons/{comparison_id}",
        response_model=DecisionComparison,
        tags=["comparisons"],
    )
    def get_decision_comparison(comparison_id: str):
        try:
            return repository.get_decision_comparison(comparison_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/consensus-dossiers",
        response_model=ConsensusDossier,
        status_code=201,
        tags=["consensus"],
    )
    def create_consensus_dossier(data: ConsensusDossierCreate):
        try:
            return repository.create_consensus_dossier(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/v1/consensus-dossiers/{dossier_id}",
        response_model=ConsensusDossier,
        tags=["consensus"],
    )
    def get_consensus_dossier(dossier_id: str):
        try:
            return repository.get_consensus_dossier(dossier_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/calibration-dossiers",
        response_model=CalibrationDossier,
        status_code=201,
        tags=["calibration"],
    )
    def create_calibration_dossier(data: CalibrationDossierCreate):
        try:
            return repository.create_calibration_dossier(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get(
        "/v1/calibration-dossiers",
        response_model=list[CalibrationDossier],
        tags=["calibration"],
    )
    def list_calibration_dossiers():
        return repository.list_calibration_dossiers()

    @application.get(
        "/v1/calibration-dossiers/{dossier_id}",
        response_model=CalibrationDossier,
        tags=["calibration"],
    )
    def get_calibration_dossier(dossier_id: str):
        try:
            return repository.get_calibration_dossier(dossier_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/decision-stability-dossiers",
        response_model=DecisionStabilityDossier,
        status_code=201,
        tags=["stability"],
    )
    def create_decision_stability_dossier(data: DecisionStabilityDossierCreate):
        try:
            return repository.create_decision_stability_dossier(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/v1/decision-stability-dossiers",
        response_model=list[DecisionStabilityDossier],
        tags=["stability"],
    )
    def list_decision_stability_dossiers():
        return repository.list_decision_stability_dossiers()

    @application.get(
        "/v1/decision-stability-dossiers/{dossier_id}",
        response_model=DecisionStabilityDossier,
        tags=["stability"],
    )
    def get_decision_stability_dossier(dossier_id: str):
        try:
            return repository.get_decision_stability_dossier(dossier_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/decision-change-attribution-dossiers",
        response_model=DecisionChangeAttributionDossier,
        status_code=201,
        tags=["attribution"],
    )
    def create_decision_change_attribution_dossier(
        data: DecisionChangeAttributionDossierCreate,
    ):
        try:
            return repository.create_decision_change_attribution_dossier(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/v1/decision-change-attribution-dossiers",
        response_model=list[DecisionChangeAttributionDossier],
        tags=["attribution"],
    )
    def list_decision_change_attribution_dossiers():
        return repository.list_decision_change_attribution_dossiers()

    @application.get(
        "/v1/decision-change-attribution-dossiers/{dossier_id}",
        response_model=DecisionChangeAttributionDossier,
        tags=["attribution"],
    )
    def get_decision_change_attribution_dossier(dossier_id: str):
        try:
            return repository.get_decision_change_attribution_dossier(dossier_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post(
        "/v1/criterion-coverage-dossiers",
        response_model=CriterionCoverageDossier,
        status_code=201,
        tags=["coverage"],
    )
    def create_criterion_coverage_dossier(data: CriterionCoverageDossierCreate):
        try:
            return repository.create_criterion_coverage_dossier(data)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @application.get(
        "/v1/criterion-coverage-dossiers",
        response_model=list[CriterionCoverageDossier],
        tags=["coverage"],
    )
    def list_criterion_coverage_dossiers():
        return repository.list_criterion_coverage_dossiers()

    @application.get(
        "/v1/criterion-coverage-dossiers/{dossier_id}",
        response_model=CriterionCoverageDossier,
        tags=["coverage"],
    )
    def get_criterion_coverage_dossier(dossier_id: str):
        try:
            return repository.get_criterion_coverage_dossier(dossier_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/v1/audit-events", response_model=list[AuditEvent], tags=["audit"])
    def list_audit_events():
        return repository.list_audit_events()

    return application


app = create_app()
