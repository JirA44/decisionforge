import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from decisionforge.api import create_app
from decisionforge.models import (
    CalibrationDossierCreate,
    ConsensusDossierCreate,
    CriterionCoverageDossierCreate,
    DecisionComparisonCreate,
    DecisionCreate,
    DecisionChangeAttributionDossierCreate,
    DecisionStabilityDossierCreate,
    EvaluationCreate,
    SensitivityAnalysisCreate,
)
from decisionforge.repository import Repository


def payload(scores=(90, 60, 70, 80), confidences=(0.9, 0.9, 0.9, 0.9)):
    return {
        "title": "Choisir un hébergeur",
        "problem": "Quel hébergeur utiliser ?",
        "alternatives": [{"key": "alpha", "label": "Alpha"}, {"key": "beta", "label": "Beta"}],
        "criteria": [
            {"key": "reliability", "label": "Fiabilité", "weight": 0.7, "blocking_minimum": 60},
            {"key": "cost", "label": "Coût", "weight": 0.3},
        ],
        "observations": [
            {"alternative_key": "alpha", "criterion_key": "reliability", "score": scores[0], "confidence": confidences[0], "source_ref": "audit-a"},
            {"alternative_key": "alpha", "criterion_key": "cost", "score": scores[1], "confidence": confidences[1], "source_ref": "quote-a"},
            {"alternative_key": "beta", "criterion_key": "reliability", "score": scores[2], "confidence": confidences[2], "source_ref": "audit-b"},
            {"alternative_key": "beta", "criterion_key": "cost", "score": scores[3], "confidence": confidences[3], "source_ref": "quote-b"},
        ],
    }


def sensitivity_payload(alpha=(90, 90), beta=(60, 60)):
    return {
        "title": "Choisir une option",
        "problem": "Quelle option résiste à une variation des poids ?",
        "alternatives": [{"key": "alpha", "label": "Alpha"}, {"key": "beta", "label": "Beta"}],
        "criteria": [
            {"key": "quality", "label": "Qualité", "weight": 0.5},
            {"key": "cost", "label": "Coût", "weight": 0.5},
        ],
        "observations": [
            {"alternative_key": "alpha", "criterion_key": "quality", "score": alpha[0], "confidence": 1, "source_ref": "a1"},
            {"alternative_key": "alpha", "criterion_key": "cost", "score": alpha[1], "confidence": 1, "source_ref": "a2"},
            {"alternative_key": "beta", "criterion_key": "quality", "score": beta[0], "confidence": 1, "source_ref": "b1"},
            {"alternative_key": "beta", "criterion_key": "cost", "score": beta[1], "confidence": 1, "source_ref": "b2"},
        ],
    }


def evaluated(repository, data):
    decision = repository.create_decision(DecisionCreate.model_validate(data))
    return repository.evaluate_decision(EvaluationCreate(decision_id=decision.id))


def test_server_computes_recommendation_and_ranking(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    decision = repository.create_decision(DecisionCreate.model_validate(payload()))
    result = repository.evaluate_decision(EvaluationCreate(decision_id=decision.id))
    assert result.status == "RECOMMENDED"
    assert result.recommended_alternative_key == "alpha"
    assert result.ranking[0].alternative_key == "alpha"
    assert result.ranking[0].score == 72.9
    assert len(result.outcome_hash) == 64


def test_missing_or_low_confidence_evidence_is_insufficient(tmp_path):
    data = payload()
    data["observations"] = data["observations"][:-1]
    repository = Repository(tmp_path / "decision.db")
    decision = repository.create_decision(DecisionCreate.model_validate(data))
    result = repository.evaluate_decision(EvaluationCreate(decision_id=decision.id))
    assert result.status == "INSUFFICIENT"
    assert result.recommended_alternative_key is None
    beta = next(item for item in result.ranking if item.alternative_key == "beta")
    assert "observation manquante" in beta.insufficiencies[0]


def test_all_alternatives_below_blocking_threshold_are_blocked(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    decision = repository.create_decision(DecisionCreate.model_validate(payload(scores=(40, 90, 50, 90))))
    result = repository.evaluate_decision(EvaluationCreate(decision_id=decision.id))
    assert result.status == "BLOCKED"
    assert result.recommended_alternative_key is None
    assert all(item.blockers for item in result.ranking)


def test_exact_tie_does_not_invent_a_winner(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    decision = repository.create_decision(DecisionCreate.model_validate(payload(scores=(80, 80, 80, 80))))
    result = repository.evaluate_decision(EvaluationCreate(decision_id=decision.id))
    assert result.status == "INSUFFICIENT"
    assert result.recommended_alternative_key is None
    assert result.ranking[0].rank == result.ranking[1].rank == 1


def test_creation_and_evaluation_are_idempotent(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    specification = DecisionCreate.model_validate(payload())
    first_decision = repository.create_decision(specification)
    second_decision = repository.create_decision(specification)
    assert second_decision.id == first_decision.id
    first = repository.evaluate_decision(EvaluationCreate(decision_id=first_decision.id))
    replay = repository.evaluate_decision(EvaluationCreate(decision_id=first_decision.id))
    assert replay.id == first.id
    assert replay.outcome_hash == first.outcome_hash
    assert replay.idempotent_replay is True
    assert [event.event_type for event in repository.list_audit_events()] == [
        "DECISION_SNAPSHOT_FROZEN",
        "DECISION_EVALUATED",
    ]


def test_storage_rejects_updates_and_deletes(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    decision = repository.create_decision(DecisionCreate.model_validate(payload()))
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("UPDATE decision_snapshots SET created_at = 'changed' WHERE id = ?", (decision.id,))
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="append-only"):
        connection.execute("DELETE FROM audit_events")


def test_strict_validation_rejects_client_verdict_and_unknown_references():
    invalid = payload()
    invalid["verdict"] = "RECOMMENDED"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionCreate.model_validate(invalid)
    invalid_reference = payload()
    invalid_reference["observations"][0]["alternative_key"] = "ghost"
    with pytest.raises(ValidationError, match="unknown alternative"):
        DecisionCreate.model_validate(invalid_reference)


def test_api_health_and_client_cannot_submit_outcome(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok", "version": "1.0.7", "database": "ok"}
        info = client.get("/info")
        assert info.status_code == 200
        assert info.json() == {
            "name": "DecisionForge",
            "version": "1.0.7",
            "consensus_method": "evaluation-consensus-v1",
            "calibration_method": "decision-calibration-v1",
            "stability_method": "decision-stability-timeline-v1",
            "attribution_method": "decision-change-attribution-v1",
            "criterion_coverage_method": "criterion-coverage-dossier-v1",
            "automatic_action": False,
        }
        created = client.post("/v1/decisions", json=payload())
        assert created.status_code == 201
        response = client.post(
            "/v1/evaluations",
            json={"decision_id": created.json()["id"], "verdict": "RECOMMENDED", "rank": 1},
        )
        assert response.status_code == 422


def test_static_and_runtime_openapi_31_cover_all_routes(tmp_path):
    import yaml

    static = yaml.safe_load((Path(__file__).parents[1] / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
    runtime = create_app(tmp_path / "openapi.db").openapi()
    expected = {
        "/health",
        "/info",
        "/v1/decisions",
        "/v1/decisions/{decision_id}",
        "/v1/evaluations",
        "/v1/evaluations/{evaluation_id}",
        "/v1/sensitivity-analyses",
        "/v1/sensitivity-analyses/{analysis_id}",
        "/v1/decision-comparisons",
        "/v1/decision-comparisons/{comparison_id}",
        "/v1/consensus-dossiers",
        "/v1/consensus-dossiers/{dossier_id}",
        "/v1/calibration-dossiers",
        "/v1/calibration-dossiers/{dossier_id}",
        "/v1/decision-stability-dossiers",
        "/v1/decision-stability-dossiers/{dossier_id}",
        "/v1/decision-change-attribution-dossiers",
        "/v1/decision-change-attribution-dossiers/{dossier_id}",
        "/v1/criterion-coverage-dossiers",
        "/v1/criterion-coverage-dossiers/{dossier_id}",
        "/v1/audit-events",
    }
    assert static["openapi"] == "3.1.0"
    assert runtime["openapi"].startswith("3.1.")
    assert static["info"]["version"] == runtime["info"]["version"] == "1.0.7"
    assert set(static["paths"]) == set(runtime["paths"]) == expected


def coverage_evaluations(repository, variants):
    results = []
    for index, data in enumerate(variants):
        data = {**data, "context": f"snapshot-{index}"}
        results.append(evaluated(repository, data))
    return results


def test_criterion_coverage_complete_and_hashed(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = coverage_evaluations(repository, [payload(), payload(scores=(88, 62, 72, 78))])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert result.qualification == "COMPLETE"
    assert result.compatible is True
    assert result.common_covered_criterion_keys == ["cost", "reliability"]
    assert result.gap_criterion_keys == []
    assert result.minimum_overall_coverage == 1.0
    assert len(result.evidence_hash) == len(result.dossier_hash) == 64


def test_criterion_coverage_partial_for_optional_gap(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    first = payload()
    second = payload(scores=(88, 62, 72, 78))
    for data in (first, second):
        data["criteria"][1]["required"] = False
    second["observations"] = [
        item for item in second["observations"]
        if not (item["alternative_key"] == "beta" and item["criterion_key"] == "cost")
    ]
    evaluations = coverage_evaluations(repository, [first, second])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert result.qualification == "PARTIAL"
    assert result.gap_criterion_keys == ["cost"]
    cost = next(item for item in result.criteria if item.criterion_key == "cost")
    assert cost.minimum_coverage == 0.5
    assert cost.fully_covered_evaluation_count == 1


def test_criterion_coverage_insufficient_when_recomputed_evaluation_is_inconclusive(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    incomplete = payload()
    incomplete["observations"] = incomplete["observations"][:-1]
    evaluations = coverage_evaluations(repository, [payload(), incomplete])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert result.qualification == "INSUFFICIENT"
    assert result.minimum_overall_coverage == 0.75
    assert result.worst_evaluation.evaluation_id == evaluations[1].id


def test_criterion_coverage_incompatible_contracts_do_not_aggregate(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    different = payload()
    different["title"] = "Autre décision"
    evaluations = coverage_evaluations(repository, [payload(), different])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert result.qualification == "INCOMPATIBLE"
    assert result.compatible is False
    assert result.evaluations == result.criteria == []
    assert result.worst_evaluation is None


def test_criterion_coverage_is_order_independent_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = coverage_evaluations(repository, [payload(), payload(scores=(88, 62, 72, 78))])
    first = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    replay = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in reversed(evaluations)])
    )
    assert replay.id == first.id
    assert replay.dossier_hash == first.dossier_hash
    assert replay.idempotent_replay is True
    assert first.evaluation_ids == sorted(item.id for item in evaluations)
    assert sum(event.event_type == "CRITERION_COVERAGE_DOSSIER_FROZEN" for event in repository.list_audit_events()) == 1


def test_criterion_coverage_request_is_strict_bounded_and_unique():
    with pytest.raises(ValidationError, match="at least 2"):
        CriterionCoverageDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError, match="must be unique"):
        CriterionCoverageDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError, match="at most 100"):
        CriterionCoverageDossierCreate(evaluation_ids=[f"evaluation-{index}" for index in range(101)])
    with pytest.raises(ValidationError, match="must not be blank"):
        CriterionCoverageDossierCreate(evaluation_ids=["one", "   "])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CriterionCoverageDossierCreate.model_validate(
            {"evaluation_ids": ["one", "two"], "qualification": "COMPLETE"}
        )


def test_criterion_coverage_api_post_get_list_and_unknown_reference(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        ids = []
        for index in range(2):
            data = payload(scores=(90 - index, 60 + index, 70 + index, 80 - index))
            data["context"] = f"api-{index}"
            decision = client.post("/v1/decisions", json=data).json()
            ids.append(client.post("/v1/evaluations", json={"decision_id": decision["id"]}).json()["id"])
        created = client.post("/v1/criterion-coverage-dossiers", json={"evaluation_ids": ids})
        assert created.status_code == 201
        dossier_id = created.json()["id"]
        assert client.get(f"/v1/criterion-coverage-dossiers/{dossier_id}").json()["dossier_hash"] == created.json()["dossier_hash"]
        assert [item["id"] for item in client.get("/v1/criterion-coverage-dossiers").json()] == [dossier_id]
        assert client.post("/v1/criterion-coverage-dossiers", json={"evaluation_ids": [ids[0], "missing"]}).status_code == 404


def test_criterion_coverage_storage_is_immutable(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluations = coverage_evaluations(repository, [payload(), payload(scores=(88, 62, 72, 78))])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE criterion_coverage_dossiers SET qualification='PARTIAL' WHERE id=?", (result.id,)
        )


def test_criterion_coverage_evidence_references_server_recalculation(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = coverage_evaluations(repository, [payload(), payload(scores=(88, 62, 72, 78))])
    result = repository.create_criterion_coverage_dossier(
        CriterionCoverageDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert result.chronological_evaluation_ids == [item.id for item in evaluations]
    assert [item.recomputed_outcome_hash for item in result.evaluations] == [
        item.outcome_hash for item in evaluations
    ]
    assert all(item.decision_hash for item in result.evaluations)


def test_sensitivity_qualifies_robust_winner_and_bounded_scenarios(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluation = evaluated(repository, sensitivity_payload())
    result = repository.analyze_evaluation(SensitivityAnalysisCreate(evaluation_id=evaluation.id))
    assert result.qualification == "ROBUST"
    assert result.baseline_winner_alternative_key == "alpha"
    assert result.winner_stability == 1.0
    assert result.minimum_winner_margin == 30.0
    assert len(result.scenarios) == 5
    assert all(abs(sum(item.normalized_weights.values()) - 1) < 1e-9 for item in result.scenarios)
    assert {item.direction for item in result.scenarios} == {"BASELINE", "DECREASE", "INCREASE"}
    assert len(result.analysis_hash) == 64


def test_sensitivity_qualifies_fragile_when_winner_changes(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluation = evaluated(repository, sensitivity_payload(alpha=(100, 0), beta=(0, 98)))
    result = repository.analyze_evaluation(SensitivityAnalysisCreate(evaluation_id=evaluation.id))
    assert result.qualification == "FRAGILE"
    assert result.baseline_winner_alternative_key == "alpha"
    assert result.winner_stability == 0.5
    assert {item.winner_alternative_key for item in result.scenarios} == {"alpha", "beta"}
    assert "n'est pas conservé" in result.reasons[0]


def test_sensitivity_is_insufficient_without_unique_baseline_winner(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluation = evaluated(repository, sensitivity_payload(alpha=(80, 80), beta=(80, 80)))
    assert evaluation.status == "INSUFFICIENT"
    result = repository.analyze_evaluation(SensitivityAnalysisCreate(evaluation_id=evaluation.id))
    assert result.qualification == "INSUFFICIENT"
    assert result.baseline_winner_alternative_key is None
    assert result.winner_stability == 0.0
    assert result.minimum_winner_margin is None


def test_sensitivity_is_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluation = evaluated(repository, sensitivity_payload())
    request = SensitivityAnalysisCreate(evaluation_id=evaluation.id)
    first = repository.analyze_evaluation(request)
    replay = repository.analyze_evaluation(request)
    assert replay.id == first.id
    assert replay.analysis_hash == first.analysis_hash
    assert replay.idempotent_replay is True
    assert [event.event_type for event in repository.list_audit_events()] == [
        "DECISION_SNAPSHOT_FROZEN",
        "DECISION_EVALUATED",
        "SENSITIVITY_ANALYSIS_FROZEN",
    ]


def test_sensitivity_rejects_client_qualification_and_unknown_fields(tmp_path):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SensitivityAnalysisCreate.model_validate(
            {"evaluation_id": "evaluation-1", "qualification": "ROBUST"}
        )
    with TestClient(create_app(tmp_path / "api.db")) as client:
        decision = client.post("/v1/decisions", json=sensitivity_payload()).json()
        evaluation = client.post("/v1/evaluations", json={"decision_id": decision["id"]}).json()
        response = client.post(
            "/v1/sensitivity-analyses",
            json={"evaluation_id": evaluation["id"], "winner": "alpha", "action": "approve"},
        )
        assert response.status_code == 422


def test_sensitivity_snapshot_is_immutable_in_model_and_storage(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluation = evaluated(repository, sensitivity_payload())
    result = repository.analyze_evaluation(SensitivityAnalysisCreate(evaluation_id=evaluation.id))
    with pytest.raises(ValidationError, match="frozen"):
        result.qualification = "FRAGILE"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE sensitivity_analyses SET qualification = 'FRAGILE' WHERE id = ?", (result.id,)
        )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM sensitivity_analyses WHERE id = ?", (result.id,))


def comparison_pair(repository, baseline_data, candidate_data):
    baseline = evaluated(repository, baseline_data)
    candidate = evaluated(repository, candidate_data)
    return baseline, candidate


def test_comparison_is_consistent_and_recomputed_from_observations(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    candidate_data = payload()
    candidate_data["context"] = "Snapshot candidat indépendant, mêmes preuves."
    baseline, candidate = comparison_pair(repository, payload(), candidate_data)
    result = repository.compare_evaluations(
        DecisionComparisonCreate(
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
        )
    )
    assert result.qualification == "CONSISTENT"
    assert result.compatible is True
    assert result.recommendation_changed is False
    assert result.status_changed is False
    assert result.ranking_changed is False
    assert result.baseline.recomputed_outcome_hash == baseline.outcome_hash
    assert result.candidate.recomputed_outcome_hash == candidate.outcome_hash
    assert result.winner_margin_change == 0.0
    assert len(result.comparison_hash) == 64


def test_comparison_detects_changed_recommendation_ranks_scores_and_margin(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    baseline, candidate = comparison_pair(
        repository,
        payload(),
        payload(scores=(65, 60, 95, 90)),
    )
    result = repository.compare_evaluations(
        DecisionComparisonCreate(
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
        )
    )
    assert result.qualification == "CHANGED"
    assert result.baseline.recommended_alternative_key == "alpha"
    assert result.candidate.recommended_alternative_key == "beta"
    assert result.recommendation_changed is True
    assert result.ranking_changed is True
    assert result.status_changed is False
    alpha = next(item for item in result.alternatives if item.alternative_key == "alpha")
    beta = next(item for item in result.alternatives if item.alternative_key == "beta")
    assert alpha.rank_change == -1
    assert beta.rank_change == 1
    assert alpha.score_change < 0
    assert beta.score_change > 0
    assert any("recommandation" in reason.lower() for reason in result.explanations)


def test_comparison_rejects_incompatible_alternative_or_criterion_contract(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    incompatible = payload()
    incompatible["alternatives"][1]["key"] = "gamma"
    for observation in incompatible["observations"]:
        if observation["alternative_key"] == "beta":
            observation["alternative_key"] = "gamma"
    incompatible["criteria"][0]["minimum_confidence"] = 0.8
    baseline, candidate = comparison_pair(repository, payload(), incompatible)
    result = repository.compare_evaluations(
        DecisionComparisonCreate(
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
        )
    )
    assert result.qualification == "INCOMPATIBLE"
    assert result.compatible is False
    assert result.alternatives == []
    assert any("alternatives incompatibles" in reason for reason in result.explanations)
    assert any("critères incompatibles" in reason for reason in result.explanations)


def test_comparison_is_insufficient_if_one_recomputed_evaluation_is_insufficient(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    incomplete = payload()
    incomplete["observations"] = incomplete["observations"][:-1]
    baseline, candidate = comparison_pair(repository, payload(), incomplete)
    result = repository.compare_evaluations(
        DecisionComparisonCreate(
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
        )
    )
    assert result.qualification == "INSUFFICIENT"
    assert result.candidate.status == "INSUFFICIENT"
    assert result.candidate.recommended_alternative_key is None


def test_comparison_is_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    candidate_data = payload()
    candidate_data["context"] = "candidate"
    baseline, candidate = comparison_pair(repository, payload(), candidate_data)
    request = DecisionComparisonCreate(
        baseline_evaluation_id=baseline.id,
        candidate_evaluation_id=candidate.id,
    )
    first = repository.compare_evaluations(request)
    replay = repository.compare_evaluations(request)
    assert replay.id == first.id
    assert replay.comparison_hash == first.comparison_hash
    assert replay.idempotent_replay is True
    assert [event.event_type for event in repository.list_audit_events()].count(
        "DECISION_COMPARISON_FROZEN"
    ) == 1


def test_comparison_snapshot_is_immutable_in_model_and_storage(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    candidate_data = payload()
    candidate_data["context"] = "candidate"
    baseline, candidate = comparison_pair(repository, payload(), candidate_data)
    result = repository.compare_evaluations(
        DecisionComparisonCreate(
            baseline_evaluation_id=baseline.id,
            candidate_evaluation_id=candidate.id,
        )
    )
    with pytest.raises(ValidationError, match="frozen"):
        result.qualification = "CHANGED"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE decision_comparisons SET qualification = 'CHANGED' WHERE id = ?", (result.id,)
        )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM decision_comparisons WHERE id = ?", (result.id,))


def test_comparison_accepts_only_ids_and_forbids_client_results(tmp_path):
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionComparisonCreate.model_validate(
            {
                "baseline_evaluation_id": "baseline",
                "candidate_evaluation_id": "candidate",
                "method": "decision-comparison-v1",
                "qualification": "CONSISTENT",
                "action": "approve",
            }
        )
    with TestClient(create_app(tmp_path / "api.db")) as client:
        response = client.post(
            "/v1/decision-comparisons",
            json={
                "baseline_evaluation_id": "baseline",
                "candidate_evaluation_id": "candidate",
                "verdict": "CHANGED",
            },
        )
        assert response.status_code == 422


def consensus_evaluations(repository, score_sets):
    results = []
    for index, scores in enumerate(score_sets):
        data = payload(scores=scores)
        data["context"] = f"Snapshot de collecte {index}"
        for observation in data["observations"]:
            observation["source_ref"] += f"-{index}"
        results.append(evaluated(repository, data))
    return results


def create_consensus(repository, score_sets):
    evaluations = consensus_evaluations(repository, score_sets)
    dossier = repository.create_consensus_dossier(
        ConsensusDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    return evaluations, dossier


def test_consensus_input_requires_three_to_fifty_unique_ids_and_forbids_results():
    with pytest.raises(ValidationError):
        ConsensusDossierCreate(evaluation_ids=["one", "two"])
    with pytest.raises(ValidationError, match="must be unique"):
        ConsensusDossierCreate(evaluation_ids=["one", "two", "one"])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConsensusDossierCreate.model_validate(
            {
                "evaluation_ids": ["one", "two", "three"],
                "winner": "alpha",
                "score": 100,
                "verdict": "CONSENSUS",
                "action": "approve",
            }
        )


def test_consensus_recomputes_all_evaluations_and_aggregates_metrics(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations, dossier = create_consensus(
        repository,
        [(90, 60, 70, 80), (88, 62, 72, 78), (92, 58, 68, 82)],
    )
    assert dossier.qualification == "CONSENSUS"
    assert dossier.compatible is True
    assert dossier.majority_alternative_key == "alpha"
    assert dossier.majority_share == 1.0
    assert dossier.evaluation_count == dossier.sufficient_evaluation_count == 3
    assert [item.evaluation_id for item in dossier.evaluations] == sorted(
        item.id for item in evaluations
    )
    assert all(
        snapshot.recomputed_outcome_hash
        == next(item.outcome_hash for item in evaluations if item.id == snapshot.evaluation_id)
        for snapshot in dossier.evaluations
    )
    alpha = next(item for item in dossier.alternatives if item.alternative_key == "alpha")
    assert alpha.recommendation_count == 3
    assert alpha.recommendation_share == 1.0
    assert alpha.average_rank == 1.0
    assert alpha.score_dispersion > 0
    assert alpha.minimum_coverage == 1.0
    assert alpha.all_eligible is True
    assert dossier.minimum_winner_margin is not None
    assert len(dossier.input_hash) == len(dossier.dossier_hash) == 64


def test_consensus_qualifies_exact_two_thirds_as_stable_majority(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    _, dossier = create_consensus(
        repository,
        [(90, 60, 70, 80), (88, 62, 72, 78), (65, 60, 95, 90)],
    )
    assert dossier.qualification == "STABLE_MAJORITY"
    assert dossier.majority_alternative_key == "alpha"
    assert dossier.majority_share == 0.666667
    assert dossier.sufficient_evaluation_count == 3


def test_consensus_qualifies_divided_below_two_thirds(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    _, dossier = create_consensus(
        repository,
        [
            (90, 60, 70, 80),
            (88, 62, 72, 78),
            (65, 60, 95, 90),
            (66, 61, 94, 89),
        ],
    )
    assert dossier.qualification == "DIVIDED"
    assert dossier.majority_alternative_key is None
    assert dossier.majority_share == 0.0


def test_consensus_is_insufficient_when_one_snapshot_lacks_required_evidence(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    complete = consensus_evaluations(repository, [(90, 60, 70, 80), (88, 62, 72, 78)])
    incomplete = payload(scores=(92, 58, 68, 82))
    incomplete["context"] = "Snapshot incomplet"
    incomplete["observations"] = incomplete["observations"][:-1]
    incomplete_evaluation = evaluated(repository, incomplete)
    dossier = repository.create_consensus_dossier(
        ConsensusDossierCreate(
            evaluation_ids=[item.id for item in complete] + [incomplete_evaluation.id]
        )
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.sufficient_evaluation_count == 2
    assert any(item.status == "INSUFFICIENT" for item in dossier.evaluations)


def test_consensus_is_incompatible_for_different_decision_or_contract(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    compatible = consensus_evaluations(repository, [(90, 60, 70, 80), (88, 62, 72, 78)])
    incompatible = payload(scores=(92, 58, 68, 82))
    incompatible["problem"] = "Une autre décision ?"
    incompatible["criteria"][0]["weight"] = 0.6
    incompatible["criteria"][1]["weight"] = 0.4
    incompatible_evaluation = evaluated(repository, incompatible)
    dossier = repository.create_consensus_dossier(
        ConsensusDossierCreate(
            evaluation_ids=[item.id for item in compatible] + [incompatible_evaluation.id]
        )
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert dossier.compatible is False
    assert dossier.alternatives == []
    assert any("même décision" in item for item in dossier.explanations)
    assert any("contrats de critères" in item for item in dossier.explanations)


def test_consensus_is_order_independent_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = consensus_evaluations(
        repository, [(90, 60, 70, 80), (88, 62, 72, 78), (92, 58, 68, 82)]
    )
    ids = [item.id for item in evaluations]
    first = repository.create_consensus_dossier(ConsensusDossierCreate(evaluation_ids=ids))
    replay = repository.create_consensus_dossier(
        ConsensusDossierCreate(evaluation_ids=list(reversed(ids)))
    )
    assert replay.id == first.id
    assert replay.dossier_hash == first.dossier_hash
    assert replay.evaluation_ids == sorted(ids)
    assert replay.idempotent_replay is True
    assert [item.event_type for item in repository.list_audit_events()].count(
        "CONSENSUS_DOSSIER_FROZEN"
    ) == 1


def test_consensus_snapshot_is_immutable_in_model_and_storage(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    _, dossier = create_consensus(
        repository, [(90, 60, 70, 80), (88, 62, 72, 78), (92, 58, 68, 82)]
    )
    with pytest.raises(ValidationError, match="frozen"):
        dossier.qualification = "DIVIDED"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE consensus_dossiers SET qualification = 'DIVIDED' WHERE id = ?", (dossier.id,)
        )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM consensus_dossiers WHERE id = ?", (dossier.id,))


def test_consensus_api_accepts_only_ids_and_gets_frozen_dossier(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        evaluation_ids = []
        for index, scores in enumerate(
            [(90, 60, 70, 80), (88, 62, 72, 78), (92, 58, 68, 82)]
        ):
            data = payload(scores=scores)
            data["context"] = f"api-{index}"
            decision = client.post("/v1/decisions", json=data)
            evaluation = client.post(
                "/v1/evaluations", json={"decision_id": decision.json()["id"]}
            )
            evaluation_ids.append(evaluation.json()["id"])
        created = client.post(
            "/v1/consensus-dossiers", json={"evaluation_ids": evaluation_ids}
        )
        assert created.status_code == 201
        assert created.json()["qualification"] == "CONSENSUS"
        fetched = client.get(f"/v1/consensus-dossiers/{created.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["dossier_hash"] == created.json()["dossier_hash"]
        rejected = client.post(
            "/v1/consensus-dossiers",
            json={"evaluation_ids": evaluation_ids, "winner": "alpha", "verdict": "CONSENSUS"},
        )
        assert rejected.status_code == 422


def calibration_evaluations(repository, count, *, probability=0.8, correct_count=None):
    correct_count = count if correct_count is None else correct_count
    results = []
    for index in range(count):
        data = payload(scores=(90 + (index % 3), 60, 70, 80))
        data["context"] = f"Calibration {index}"
        data["forecast_outcome"] = {
            "predicted_probabilities": {"alpha": probability, "beta": 1 - probability},
            "observed_alternative_key": "alpha" if index < correct_count else "beta",
            "prediction_ref": f"forecast-{index}",
            "outcome_ref": f"outcome-{index}",
        }
        results.append(evaluated(repository, data))
    return results


def test_forecast_outcome_and_calibration_input_are_strict():
    invalid_sum = payload()
    invalid_sum["forecast_outcome"] = {
        "predicted_probabilities": {"alpha": 0.8, "beta": 0.3},
        "observed_alternative_key": "alpha",
        "prediction_ref": "forecast",
        "outcome_ref": "outcome",
    }
    with pytest.raises(ValidationError, match="sum to 1"):
        DecisionCreate.model_validate(invalid_sum)
    with pytest.raises(ValidationError, match="must be unique"):
        CalibrationDossierCreate(evaluation_ids=["one", "two", "one"])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CalibrationDossierCreate.model_validate(
            {
                "evaluation_ids": ["one", "two", "three"],
                "verdict": "CALIBRATED",
                "score": 0,
                "winner": "alpha",
            }
        )


def test_calibration_qualifies_well_aligned_forecasts_and_metrics(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 30, probability=0.8, correct_count=24)
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "CALIBRATED"
    assert dossier.compatible is True
    assert dossier.coverage == 1.0
    assert dossier.usable_evaluation_count == 30
    assert dossier.brier_score == 0.16
    assert dossier.bounded_log_loss is not None and dossier.bounded_log_loss < 0.7
    assert dossier.expected_calibration_error == 0.0
    assert dossier.resolution == 0.0
    assert dossier.worst_bin_index == 8
    assert len(dossier.bins) == 10
    assert dossier.bins[8].count == 30
    assert all(
        snapshot.recomputed_outcome_hash
        == next(item.outcome_hash for item in evaluations if item.id == snapshot.evaluation_id)
        for snapshot in dossier.evaluations
    )


def test_calibration_qualifies_misaligned_and_bounds_log_loss(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 30, probability=1.0, correct_count=0)
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "MISALIGNED"
    assert dossier.bounded_log_loss == 20.0
    assert dossier.expected_calibration_error == 1.0
    assert dossier.worst_bin_index == 9
    assert dossier.bins[9].calibration_gap == 1.0


def test_calibration_is_insufficient_below_fixed_sample_threshold(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 3, probability=0.8, correct_count=3)
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.coverage == 1.0
    assert any("Au moins 30" in item for item in dossier.explanations)


def test_calibration_is_insufficient_when_forecast_or_outcome_is_missing(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 29, probability=0.8, correct_count=23)
    missing = payload(scores=(89, 60, 70, 80))
    missing["context"] = "Résultat de calibration absent"
    evaluations.append(evaluated(repository, missing))
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert dossier.usable_evaluation_count == 29
    assert dossier.coverage == 0.966667


def test_calibration_rejects_incompatible_decision_contracts(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 29, probability=0.8, correct_count=24)
    incompatible = payload(scores=(90, 60, 70, 80))
    incompatible["problem"] = "Autre décision à calibrer ?"
    incompatible["forecast_outcome"] = {
        "predicted_probabilities": {"alpha": 0.8, "beta": 0.2},
        "observed_alternative_key": "alpha",
        "prediction_ref": "other-forecast",
        "outcome_ref": "other-outcome",
    }
    evaluations.append(evaluated(repository, incompatible))
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert dossier.compatible is False
    assert any("même décision" in item for item in dossier.explanations)


def test_calibration_is_order_independent_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = calibration_evaluations(repository, 3, probability=0.8, correct_count=2)
    ids = [item.id for item in evaluations]
    first = repository.create_calibration_dossier(CalibrationDossierCreate(evaluation_ids=ids))
    replay = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=list(reversed(ids)))
    )
    assert replay.id == first.id
    assert replay.dossier_hash == first.dossier_hash
    assert replay.evaluation_ids == sorted(ids)
    assert replay.idempotent_replay is True
    assert [item.event_type for item in repository.list_audit_events()].count(
        "CALIBRATION_DOSSIER_FROZEN"
    ) == 1


def test_calibration_snapshot_is_immutable_and_listed(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluations = calibration_evaluations(repository, 3, probability=0.8, correct_count=2)
    dossier = repository.create_calibration_dossier(
        CalibrationDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert [item.id for item in repository.list_calibration_dossiers()] == [dossier.id]
    with pytest.raises(ValidationError, match="frozen"):
        dossier.qualification = "CALIBRATED"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE calibration_dossiers SET qualification = 'CALIBRATED' WHERE id = ?", (dossier.id,)
        )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM calibration_dossiers WHERE id = ?", (dossier.id,))


def test_calibration_api_post_get_list_and_rejects_client_verdict(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        evaluation_ids = []
        for index in range(3):
            data = payload(scores=(90 + index, 60, 70, 80))
            data["context"] = f"api-calibration-{index}"
            data["forecast_outcome"] = {
                "predicted_probabilities": {"alpha": 0.8, "beta": 0.2},
                "observed_alternative_key": "alpha",
                "prediction_ref": f"api-forecast-{index}",
                "outcome_ref": f"api-outcome-{index}",
            }
            decision = client.post("/v1/decisions", json=data).json()
            evaluation = client.post(
                "/v1/evaluations", json={"decision_id": decision["id"]}
            ).json()
            evaluation_ids.append(evaluation["id"])
        created = client.post(
            "/v1/calibration-dossiers", json={"evaluation_ids": evaluation_ids}
        )
        assert created.status_code == 201
        fetched = client.get(f"/v1/calibration-dossiers/{created.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["dossier_hash"] == created.json()["dossier_hash"]
        listed = client.get("/v1/calibration-dossiers")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [created.json()["id"]]
        rejected = client.post(
            "/v1/calibration-dossiers",
            json={"evaluation_ids": evaluation_ids, "verdict": "CALIBRATED", "action": "approve"},
        )
        assert rejected.status_code == 422


def stability_evaluation(repository, *, scores=(90, 60, 70, 80), suffix="1", mutate=None):
    data = payload(scores=scores)
    data["context"] = f"constat chronologique {suffix}"
    for observation in data["observations"]:
        observation["source_ref"] = f"{observation['source_ref']}-{suffix}"
    if mutate is not None:
        mutate(data)
    return evaluated(repository, data)


def test_decision_stability_qualifies_stable_and_computes_series(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = [
        stability_evaluation(repository, scores=(90, 60, 70, 80), suffix="a"),
        stability_evaluation(repository, scores=(92, 58, 71, 79), suffix="b"),
        stability_evaluation(repository, scores=(91, 61, 69, 78), suffix="c"),
    ]
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[item.id for item in reversed(evaluations)])
    )
    assert dossier.qualification == "STABLE"
    assert dossier.chronological_evaluation_ids == [item.id for item in evaluations]
    assert dossier.status_transition_count == dossier.recommendation_transition_count == 0
    assert dossier.longest_status_streak == dossier.longest_recommendation_streak == 3
    assert dossier.first_recommendation == dossier.last_recommendation == "alpha"
    assert dossier.worst_coverage == 1.0
    assert len(dossier.input_hash) == len(dossier.evidence_hash) == len(dossier.dossier_hash) == 64
    assert dossier.automatic_action is False


def test_decision_stability_qualifies_drifting_on_recommendation_change(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    first = stability_evaluation(repository, scores=(95, 90, 60, 60), suffix="a")
    second = stability_evaluation(repository, scores=(60, 60, 95, 90), suffix="b")
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[second.id, first.id])
    )
    assert dossier.qualification == "DRIFTING"
    assert dossier.recommendation_transition_count == 1
    assert dossier.ranking_transition_count == 1
    assert dossier.churn_rate == 1.0
    assert dossier.first_recommendation == "alpha"
    assert dossier.last_recommendation == "beta"
    assert dossier.transitions[0].moved_alternatives == ["alpha", "beta"]


def test_decision_stability_qualifies_drifting_on_conclusive_status_change(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    recommended = stability_evaluation(repository, suffix="recommended")
    blocked = stability_evaluation(
        repository, scores=(40, 90, 50, 90), suffix="blocked"
    )
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[recommended.id, blocked.id])
    )
    assert dossier.qualification == "DRIFTING"
    assert dossier.status_transition_count == 1
    assert dossier.transitions[0].status_changed is True


def test_decision_stability_is_insufficient_when_one_evaluation_is_non_conclusive(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    complete = stability_evaluation(repository, suffix="complete")

    def remove_evidence(data):
        data["observations"].pop()

    incomplete = stability_evaluation(repository, suffix="incomplete", mutate=remove_evidence)
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[complete.id, incomplete.id])
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert any(item.status == "INSUFFICIENT" for item in dossier.evaluations)
    assert dossier.last_recommendation is None


def test_decision_stability_is_incompatible_for_another_logical_decision_or_contract(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    reference = stability_evaluation(repository, suffix="reference")

    def change_contract(data):
        data["title"] = "Choisir un autre service"
        data["criteria"][0]["weight"] = 0.6
        data["criteria"][1]["weight"] = 0.4

    incompatible = stability_evaluation(repository, suffix="other", mutate=change_contract)
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[reference.id, incompatible.id])
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert dossier.compatible is False
    assert any("même décision" in item or "critères" in item for item in dossier.explanations)


def test_decision_stability_is_order_independent_idempotent_and_audited_once(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = [stability_evaluation(repository, suffix=str(index)) for index in range(3)]
    ids = [item.id for item in evaluations]
    first = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=ids)
    )
    replay = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=list(reversed(ids)))
    )
    assert replay.id == first.id
    assert replay.input_hash == first.input_hash
    assert replay.dossier_hash == first.dossier_hash
    assert replay.evaluation_ids == sorted(ids)
    assert replay.idempotent_replay is True
    assert [event.event_type for event in repository.list_audit_events()].count(
        "DECISION_STABILITY_DOSSIER_FROZEN"
    ) == 1


def test_decision_stability_snapshot_is_immutable_gettable_and_listed(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluations = [stability_evaluation(repository, suffix=str(index)) for index in range(2)]
    dossier = repository.create_decision_stability_dossier(
        DecisionStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert repository.get_decision_stability_dossier(dossier.id).dossier_hash == dossier.dossier_hash
    assert [item.id for item in repository.list_decision_stability_dossiers()] == [dossier.id]
    with pytest.raises(ValidationError, match="frozen"):
        dossier.qualification = "DRIFTING"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE decision_stability_dossiers SET qualification = 'DRIFTING' WHERE id = ?",
            (dossier.id,),
        )
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute("DELETE FROM decision_stability_dossiers WHERE id = ?", (dossier.id,))


def test_decision_stability_strict_input_bounds_and_hash_verification(tmp_path):
    with pytest.raises(ValidationError):
        DecisionStabilityDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError, match="unique"):
        DecisionStabilityDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError):
        DecisionStabilityDossierCreate(evaluation_ids=[str(index) for index in range(101)])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionStabilityDossierCreate.model_validate(
            {"evaluation_ids": ["one", "two"], "order": ["two", "one"], "verdict": "STABLE"}
        )

    path = tmp_path / "tamper.db"
    repository = Repository(path)
    evaluations = [stability_evaluation(repository, suffix=str(index)) for index in range(2)]
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER evaluations_no_update")
        connection.execute(
            "UPDATE evaluations SET outcome_hash = ? WHERE id = ?", ("0" * 64, evaluations[1].id)
        )
    with pytest.raises(ValueError, match="does not match"):
        repository.create_decision_stability_dossier(
            DecisionStabilityDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )


def test_decision_stability_api_post_get_list_and_rejects_client_results(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        evaluation_ids = []
        for suffix in ("a", "b"):
            data = payload()
            data["context"] = f"api stability {suffix}"
            for observation in data["observations"]:
                observation["source_ref"] += suffix
            decision = client.post("/v1/decisions", json=data).json()
            evaluation = client.post("/v1/evaluations", json={"decision_id": decision["id"]}).json()
            evaluation_ids.append(evaluation["id"])
        created = client.post(
            "/v1/decision-stability-dossiers", json={"evaluation_ids": list(reversed(evaluation_ids))}
        )
        assert created.status_code == 201
        assert created.json()["chronological_evaluation_ids"] == evaluation_ids
        fetched = client.get(f"/v1/decision-stability-dossiers/{created.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["dossier_hash"] == created.json()["dossier_hash"]
        listed = client.get("/v1/decision-stability-dossiers")
        assert [item["id"] for item in listed.json()] == [created.json()["id"]]
        rejected = client.post(
            "/v1/decision-stability-dossiers",
            json={"evaluation_ids": evaluation_ids, "qualification": "STABLE", "result": {}},
        )
        assert rejected.status_code == 422


def test_change_attribution_explains_recommendation_change_and_contributions(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    first = stability_evaluation(repository, scores=(95, 90, 60, 60), suffix="before")
    second = stability_evaluation(repository, scores=(60, 60, 95, 90), suffix="after")
    dossier = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=[second.id, first.id])
    )
    assert dossier.qualification == "EXPLAINED"
    assert dossier.chronological_evaluation_ids == [first.id, second.id]
    assert dossier.changed_transition_count == dossier.explained_change_count == 1
    assert dossier.unexplained_change_count == 0
    transition = dossier.transitions[0]
    assert transition.recommendation_changed is True
    assert transition.losing_alternative_key == "alpha"
    assert transition.winning_alternative_key == "beta"
    assert transition.explained is True
    assert transition.explanation_completeness == 1.0
    assert transition.dominant_criteria
    assert transition.observation_contributions
    assert transition.criterion_contributions
    assert dossier.winning_alternatives == ["beta"]
    assert dossier.losing_alternatives == ["alpha"]
    assert dossier.worst_transition == transition
    assert len(dossier.input_hash) == len(dossier.evidence_hash) == len(dossier.dossier_hash) == 64
    assert dossier.automatic_action is False


def test_change_attribution_explains_absence_of_decision_change(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    evaluations = [
        stability_evaluation(repository, scores=(90, 60, 70, 80), suffix="a"),
        stability_evaluation(repository, scores=(91, 60, 70, 79), suffix="b"),
    ]
    dossier = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=[item.id for item in evaluations])
    )
    assert dossier.qualification == "EXPLAINED"
    assert dossier.changed_transition_count == 0
    assert dossier.explained_change_count == dossier.unexplained_change_count == 0
    assert dossier.transitions[0].change_detected is False


def test_change_attribution_is_partial_for_non_comparable_optional_observation(tmp_path):
    repository = Repository(tmp_path / "decision.db")

    def optional_cost_missing(data):
        data["criteria"][1]["required"] = False
        data["observations"] = [
            item
            for item in data["observations"]
            if not (item["alternative_key"] == "beta" and item["criterion_key"] == "cost")
        ]

    def optional_cost_present(data):
        data["criteria"][1]["required"] = False

    first = stability_evaluation(
        repository, scores=(70, 50, 70, 100), suffix="before", mutate=optional_cost_missing
    )
    second = stability_evaluation(
        repository, scores=(70, 50, 70, 100), suffix="after", mutate=optional_cost_present
    )
    assert first.recommended_alternative_key == "alpha"
    assert second.recommended_alternative_key == "beta"
    dossier = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=[first.id, second.id])
    )
    assert dossier.qualification == "PARTIAL"
    assert dossier.unexplained_change_count == 1
    transition = dossier.transitions[0]
    assert transition.explained is False
    assert transition.explanation_completeness < 1.0
    assert any(not item.comparable for item in transition.observation_contributions)
    assert transition.unexplained_reasons


def test_change_attribution_is_insufficient_with_missing_required_proof(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    complete = stability_evaluation(repository, suffix="complete")

    def remove_required(data):
        data["observations"].pop()

    incomplete = stability_evaluation(repository, suffix="incomplete", mutate=remove_required)
    dossier = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=[complete.id, incomplete.id])
    )
    assert dossier.qualification == "INSUFFICIENT"
    assert any(item.status == "INSUFFICIENT" for item in dossier.evaluations)


def test_change_attribution_is_incompatible_for_logical_decision_or_contract(tmp_path):
    repository = Repository(tmp_path / "decision.db")
    reference = stability_evaluation(repository, suffix="reference")

    def incompatible(data):
        data["problem"] = "Une autre question"
        data["criteria"][0]["weight"] = 0.6
        data["criteria"][1]["weight"] = 0.4

    other = stability_evaluation(repository, suffix="other", mutate=incompatible)
    dossier = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=[reference.id, other.id])
    )
    assert dossier.qualification == "INCOMPATIBLE"
    assert dossier.compatible is False
    assert dossier.transitions == []
    assert any("même décision" in item or "critères" in item for item in dossier.explanations)


def test_change_attribution_is_order_independent_idempotent_immutable_and_audited(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluations = [stability_evaluation(repository, suffix=str(index)) for index in range(3)]
    ids = [item.id for item in evaluations]
    first = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=ids)
    )
    replay = repository.create_decision_change_attribution_dossier(
        DecisionChangeAttributionDossierCreate(evaluation_ids=list(reversed(ids)))
    )
    assert replay.id == first.id
    assert replay.dossier_hash == first.dossier_hash
    assert replay.idempotent_replay is True
    assert repository.get_decision_change_attribution_dossier(first.id).dossier_hash == first.dossier_hash
    assert [item.id for item in repository.list_decision_change_attribution_dossiers()] == [first.id]
    assert [event.event_type for event in repository.list_audit_events()].count(
        "DECISION_CHANGE_ATTRIBUTION_DOSSIER_FROZEN"
    ) == 1
    with pytest.raises(ValidationError, match="frozen"):
        first.qualification = "PARTIAL"
    with sqlite3.connect(path) as connection, pytest.raises(sqlite3.IntegrityError, match="immutable"):
        connection.execute(
            "UPDATE decision_change_attribution_dossiers SET qualification='PARTIAL' WHERE id=?",
            (first.id,),
        )


def test_change_attribution_verifies_decision_and_outcome_hashes(tmp_path):
    path = tmp_path / "decision.db"
    repository = Repository(path)
    evaluations = [stability_evaluation(repository, suffix=str(index)) for index in range(2)]
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER evaluations_no_update")
        connection.execute(
            "UPDATE evaluations SET outcome_hash=? WHERE id=?", ("0" * 64, evaluations[1].id)
        )
    with pytest.raises(ValueError, match="does not match"):
        repository.create_decision_change_attribution_dossier(
            DecisionChangeAttributionDossierCreate(evaluation_ids=[item.id for item in evaluations])
        )


def test_change_attribution_input_is_strict_ids_only_and_bounded():
    with pytest.raises(ValidationError):
        DecisionChangeAttributionDossierCreate(evaluation_ids=["one"])
    with pytest.raises(ValidationError, match="unique"):
        DecisionChangeAttributionDossierCreate(evaluation_ids=["same", "same"])
    with pytest.raises(ValidationError):
        DecisionChangeAttributionDossierCreate(evaluation_ids=[str(index) for index in range(101)])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DecisionChangeAttributionDossierCreate.model_validate(
            {"evaluation_ids": ["one", "two"], "order": [], "verdict": "EXPLAINED", "action": "approve"}
        )


def test_change_attribution_api_post_get_list_and_rejects_client_results(tmp_path):
    with TestClient(create_app(tmp_path / "api.db")) as client:
        evaluation_ids = []
        for suffix, scores in (("a", (95, 90, 60, 60)), ("b", (60, 60, 95, 90))):
            data = payload(scores=scores)
            data["context"] = f"attribution {suffix}"
            for observation in data["observations"]:
                observation["source_ref"] += suffix
            decision = client.post("/v1/decisions", json=data).json()
            evaluation = client.post("/v1/evaluations", json={"decision_id": decision["id"]}).json()
            evaluation_ids.append(evaluation["id"])
        created = client.post(
            "/v1/decision-change-attribution-dossiers",
            json={"evaluation_ids": list(reversed(evaluation_ids))},
        )
        assert created.status_code == 201
        assert created.json()["qualification"] == "EXPLAINED"
        fetched = client.get(f"/v1/decision-change-attribution-dossiers/{created.json()['id']}")
        assert fetched.status_code == 200
        assert fetched.json()["dossier_hash"] == created.json()["dossier_hash"]
        listed = client.get("/v1/decision-change-attribution-dossiers")
        assert [item["id"] for item in listed.json()] == [created.json()["id"]]
        rejected = client.post(
            "/v1/decision-change-attribution-dossiers",
            json={"evaluation_ids": evaluation_ids, "qualification": "EXPLAINED", "result": {}},
        )
        assert rejected.status_code == 422
