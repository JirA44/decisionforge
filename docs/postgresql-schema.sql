-- DecisionForge V1.07 - schéma cible PostgreSQL 15+
CREATE TABLE decision_snapshots (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    specification_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE evaluations (
    id UUID PRIMARY KEY,
    decision_id UUID NOT NULL REFERENCES decision_snapshots(id),
    method TEXT NOT NULL CHECK (method = 'weighted-evidence-v1'),
    status TEXT NOT NULL CHECK (status IN ('RECOMMENDED', 'BLOCKED', 'INSUFFICIENT')),
    recommended_alternative_key TEXT,
    ranking_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    decision_hash CHAR(64) NOT NULL,
    outcome_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (decision_id, method)
);

CREATE TABLE sensitivity_analyses (
    id UUID PRIMARY KEY,
    evaluation_id UUID NOT NULL REFERENCES evaluations(id),
    decision_id UUID NOT NULL REFERENCES decision_snapshots(id),
    method TEXT NOT NULL CHECK (method = 'weight-sensitivity-v1'),
    policy TEXT NOT NULL CHECK (policy = 'bounded-oat-10pct-v1'),
    qualification TEXT NOT NULL CHECK (qualification IN ('ROBUST', 'FRAGILE', 'INSUFFICIENT')),
    baseline_winner_alternative_key TEXT,
    winner_stability DOUBLE PRECISION NOT NULL CHECK (winner_stability BETWEEN 0 AND 1),
    minimum_winner_margin DOUBLE PRECISION,
    scenarios_json JSONB NOT NULL,
    reasons_json JSONB NOT NULL,
    evaluation_hash CHAR(64) NOT NULL,
    analysis_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (evaluation_id, method, policy)
);

CREATE TABLE decision_comparisons (
    id UUID PRIMARY KEY,
    baseline_evaluation_id UUID NOT NULL REFERENCES evaluations(id),
    candidate_evaluation_id UUID NOT NULL REFERENCES evaluations(id),
    method TEXT NOT NULL CHECK (method = 'decision-comparison-v1'),
    qualification TEXT NOT NULL CHECK (qualification IN ('CONSISTENT', 'CHANGED', 'INCOMPATIBLE', 'INSUFFICIENT')),
    compatible BOOLEAN NOT NULL,
    baseline_json JSONB NOT NULL,
    candidate_json JSONB NOT NULL,
    recommendation_changed BOOLEAN NOT NULL,
    status_changed BOOLEAN NOT NULL,
    ranking_changed BOOLEAN NOT NULL,
    winner_margin_change DOUBLE PRECISION,
    alternatives_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    comparison_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (baseline_evaluation_id, candidate_evaluation_id, method)
);

CREATE TABLE consensus_dossiers (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    evaluation_ids_json JSONB NOT NULL,
    method TEXT NOT NULL CHECK (method = 'evaluation-consensus-v1'),
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK (qualification IN ('CONSENSUS', 'STABLE_MAJORITY', 'DIVIDED', 'INSUFFICIENT', 'INCOMPATIBLE')),
    compatible BOOLEAN NOT NULL,
    evaluation_count INTEGER NOT NULL CHECK (evaluation_count BETWEEN 3 AND 50),
    sufficient_evaluation_count INTEGER NOT NULL CHECK (sufficient_evaluation_count BETWEEN 0 AND evaluation_count),
    majority_alternative_key TEXT,
    majority_share DOUBLE PRECISION NOT NULL CHECK (majority_share BETWEEN 0 AND 1),
    evaluations_json JSONB NOT NULL,
    alternatives_json JSONB NOT NULL,
    minimum_winner_margin DOUBLE PRECISION,
    explanations_json JSONB NOT NULL,
    dossier_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE calibration_dossiers (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    evaluation_ids_json JSONB NOT NULL,
    method TEXT NOT NULL CHECK (method = 'decision-calibration-v1'),
    qualification TEXT NOT NULL CHECK (qualification IN ('CALIBRATED', 'MISALIGNED', 'INSUFFICIENT', 'INCOMPATIBLE')),
    compatible BOOLEAN NOT NULL,
    evaluation_count INTEGER NOT NULL CHECK (evaluation_count BETWEEN 3 AND 500),
    usable_evaluation_count INTEGER NOT NULL CHECK (usable_evaluation_count BETWEEN 0 AND evaluation_count),
    coverage DOUBLE PRECISION NOT NULL CHECK (coverage BETWEEN 0 AND 1),
    brier_score DOUBLE PRECISION,
    bounded_log_loss DOUBLE PRECISION CHECK (bounded_log_loss BETWEEN 0 AND 20),
    expected_calibration_error DOUBLE PRECISION,
    resolution DOUBLE PRECISION,
    worst_bin_index INTEGER CHECK (worst_bin_index BETWEEN 0 AND 9),
    evaluations_json JSONB NOT NULL,
    bins_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    dossier_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE decision_stability_dossiers (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    evaluation_ids_json JSONB NOT NULL,
    chronological_evaluation_ids_json JSONB NOT NULL,
    method TEXT NOT NULL CHECK (method = 'decision-stability-timeline-v1'),
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK (qualification IN ('STABLE', 'DRIFTING', 'INSUFFICIENT', 'INCOMPATIBLE')),
    compatible BOOLEAN NOT NULL,
    evaluation_count INTEGER NOT NULL CHECK (evaluation_count BETWEEN 2 AND 100),
    transition_count INTEGER NOT NULL,
    status_transition_count INTEGER NOT NULL,
    recommendation_transition_count INTEGER NOT NULL,
    ranking_transition_count INTEGER NOT NULL,
    churn_rate DOUBLE PRECISION NOT NULL CHECK (churn_rate BETWEEN 0 AND 1),
    longest_status_streak INTEGER NOT NULL,
    longest_recommendation_streak INTEGER NOT NULL,
    longest_unchanged_streak INTEGER NOT NULL,
    first_recommendation TEXT,
    last_recommendation TEXT,
    worst_coverage DOUBLE PRECISION NOT NULL CHECK (worst_coverage BETWEEN 0 AND 1),
    worst_winner_margin DOUBLE PRECISION,
    evaluations_json JSONB NOT NULL,
    transitions_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    dossier_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE decision_change_attribution_dossiers (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    evaluation_ids_json JSONB NOT NULL,
    chronological_evaluation_ids_json JSONB NOT NULL,
    method TEXT NOT NULL CHECK (method = 'decision-change-attribution-v1'),
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK (qualification IN ('EXPLAINED', 'PARTIAL', 'INSUFFICIENT', 'INCOMPATIBLE')),
    compatible BOOLEAN NOT NULL,
    evaluation_count INTEGER NOT NULL CHECK (evaluation_count BETWEEN 2 AND 100),
    transition_count INTEGER NOT NULL,
    changed_transition_count INTEGER NOT NULL,
    explained_change_count INTEGER NOT NULL,
    unexplained_change_count INTEGER NOT NULL,
    dominant_criteria_json JSONB NOT NULL,
    winning_alternatives_json JSONB NOT NULL,
    losing_alternatives_json JSONB NOT NULL,
    worst_transition_json JSONB,
    evaluations_json JSONB NOT NULL,
    transitions_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    dossier_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE criterion_coverage_dossiers (
    id UUID PRIMARY KEY,
    input_hash CHAR(64) NOT NULL UNIQUE,
    evaluation_ids_json JSONB NOT NULL,
    chronological_evaluation_ids_json JSONB NOT NULL,
    method TEXT NOT NULL CHECK (method = 'criterion-coverage-dossier-v1'),
    evaluation_method TEXT NOT NULL,
    qualification TEXT NOT NULL CHECK (qualification IN ('COMPLETE', 'PARTIAL', 'INSUFFICIENT', 'INCOMPATIBLE')),
    compatible BOOLEAN NOT NULL,
    evaluation_count INTEGER NOT NULL CHECK (evaluation_count BETWEEN 2 AND 100),
    criterion_count INTEGER NOT NULL CHECK (criterion_count >= 0),
    required_criterion_count INTEGER NOT NULL CHECK (required_criterion_count >= 0),
    common_covered_criterion_keys_json JSONB NOT NULL,
    gap_criterion_keys_json JSONB NOT NULL,
    minimum_overall_coverage DOUBLE PRECISION NOT NULL CHECK (minimum_overall_coverage BETWEEN 0 AND 1),
    average_overall_coverage DOUBLE PRECISION NOT NULL CHECK (average_overall_coverage BETWEEN 0 AND 1),
    worst_evaluation_json JSONB,
    evaluations_json JSONB NOT NULL,
    criteria_json JSONB NOT NULL,
    explanations_json JSONB NOT NULL,
    evidence_hash CHAR(64) NOT NULL,
    dossier_hash CHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_events (
    sequence BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE FUNCTION reject_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is immutable', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER decision_snapshots_immutable
BEFORE UPDATE OR DELETE ON decision_snapshots FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER evaluations_immutable
BEFORE UPDATE OR DELETE ON evaluations FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER sensitivity_analyses_immutable
BEFORE UPDATE OR DELETE ON sensitivity_analyses FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER decision_comparisons_immutable
BEFORE UPDATE OR DELETE ON decision_comparisons FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER consensus_dossiers_immutable
BEFORE UPDATE OR DELETE ON consensus_dossiers FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER calibration_dossiers_immutable
BEFORE UPDATE OR DELETE ON calibration_dossiers FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER decision_stability_dossiers_immutable
BEFORE UPDATE OR DELETE ON decision_stability_dossiers FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER decision_change_attribution_dossiers_immutable
BEFORE UPDATE OR DELETE ON decision_change_attribution_dossiers FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER criterion_coverage_dossiers_immutable
BEFORE UPDATE OR DELETE ON criterion_coverage_dossiers FOR EACH ROW EXECUTE FUNCTION reject_mutation();
CREATE TRIGGER audit_events_append_only
BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW EXECUTE FUNCTION reject_mutation();
