-- Prepared, NOT executed. Use only an authorised connection to the correct
-- existing PropertyAIgent database. No schema setup, refresh or evaluation.
-- These counts inventory stored rows; they do not decode matching versions
-- from fingerprints or establish final activation eligibility.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '5s';
SET LOCAL lock_timeout = '1s';
SET LOCAL idle_in_transaction_session_timeout = '15s';

SELECT status, count(*) AS stored_mandates,
       count(*) FILTER (WHERE matching_fingerprint IS NOT NULL) AS baselines_with_fingerprint,
       min(onboarding_completed_at) AS earliest_baseline,
       max(onboarding_completed_at) AS latest_baseline
FROM buyer_mandates GROUP BY status;

SELECT count(*) AS history_attempts,
       count(DISTINCT (buyer_mandate_id, subject_anchor_id, acquisition_type)) AS stored_evaluation_combinations,
       count(*) FILTER (WHERE execution_status = 'FAILED') AS failed_attempts,
       min(created_at) AS earliest_attempt, max(created_at) AS latest_attempt
FROM agent_evaluation_history;

-- evaluation_policy_version is the AGENT policy, NOT matching policy 4/5/6.
SELECT evaluation_policy_version AS agent_policy_version, prompt_version, model_id,
       execution_status, count(*) AS attempts
FROM agent_evaluation_history
GROUP BY evaluation_policy_version, prompt_version, model_id, execution_status
ORDER BY evaluation_policy_version, prompt_version, model_id, execution_status
LIMIT 200;

SELECT count(*) AS current_state_combinations,
       count(*) FILTER (WHERE current_history_id IS NULL) AS no_successful_history,
       count(*) FILTER (WHERE last_attempt_status = 'failed') AS latest_attempt_failed
FROM current_buyer_opportunity_states;

-- Distinct *stored* combinations across both sources, never sites x buyers.
SELECT count(*) AS distinct_stored_combinations FROM (
    SELECT buyer_mandate_id, subject_anchor_id, acquisition_type FROM agent_evaluation_history
    UNION
    SELECT buyer_mandate_id, subject_anchor_id, acquisition_type FROM current_buyer_opportunity_states
) AS stored;
ROLLBACK;
