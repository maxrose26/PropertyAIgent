#!/bin/bash
# Synthetic SQLite only; syscall guards prevent outbound access during tests.
set -euo pipefail
interpreter=${1:?test interpreter}; output=${2:?evidence directory}
mkdir -p "$output"
output=$(realpath "$output")
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_stage26b_b20.py tests/test_stage26b_integrity.py tests/test_stage26b_b11.py tests/test_stage26b_containment.py tests/test_stage26b_differential.py tests/test_stage2_commercial_evidence.py tests/test_stage2_unit_phasing.py \
 tests/test_mandate_explanation_trace.py tests/test_spec028_differential.py tests/test_spec028_profile.py \
 tests/test_buyer_matching.py tests/test_buyer_mandate_v2_phase_b2.py tests/test_nesten_canonical_mandate.py tests/test_wholly_affordable_state.py tests/test_acquisition_subject_identity.py tests/test_agent_evaluation_persistence.py tests/test_monitoring_detector_identity.py tests/test_opportunity_change_detection.py tests/test_opportunity_families.py tests/test_subject_relationships.py tests/test_buyer_family_feed.py tests/test_family_dashboard.py tests/test_benchmark_v6_checkpoint.py tests/test_acquisition_phasing.py tests/test_v7a_phasing_matching.py tests/test_v7_phasing_relevance.py tests/test_v7_benchmark.py tests/test_gate_b_validation.py tests/test_nesten_mandate_sync.py tests/test_opportunity_routes_strategic_scale.py tests/test_v7c_frozen_v6_oracle.py tests/test_v8_frozen_v7_oracle.py tests/test_v8_strategic_fingerprint.py tests/test_v8b_residual_opportunity.py tests/test_v8b_residual_feed.py tests/test_v8b_residual_surfaces.py tests/test_v8c_final_hardening.py tests/test_v8_monitoring_rebaseline.py tests/test_v8_ai_summary_staleness_preview.py tests/test_v8_reonboarding_differential.py tests/test_v8_rollback_tools.py tests/test_v8_stale_summary_suppression.py tests/test_allocation_intelligence_summary.py tests/test_allocation_intelligence_summary_grounding_architecture.py tests/test_allocation_intelligence_summary_trust_boundary.py tests/test_allocation_intelligence_summary_application_status_context.py tests/test_allocation_intelligence_summary_persistence_amendment.py tests/test_generate_allocation_intelligence_summaries_cli.py tests/test_allocation_discovery.py tests/test_allocation_report.py tests/test_allocation_report_pdf.py tests/test_allocation_report_pdf_gate4.py tests/test_cross_site_intelligence.py tests/test_shortlist.py tests/test_ownership_control_reporting.py tests/test_ownership_control_hierarchy.py tests/test_allocation_development_coverage.py tests/test_v7c_parity_grid.py tests/test_v7c_mandate_reonboarding.py tests/test_v7c_stale_mandate_guard.py tests/test_v7c_monitoring_preview.py tests/test_opportunity_feed.py \
 --junitxml="$output/stage2.xml" | tee "$output/stage2.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage1_spawn_offline_pytest.py -q -p no:cacheprovider \
 verification/test_stage1_access.py verification/test_stage1_buyer_scope.py verification/test_stage1_call_sites.py verification/test_stage1_commands.py \
 --junitxml="$output/security.xml" | tee "$output/security.log"
env -i HOME=/tmp PATH=/usr/bin:/bin DATABASE_URL=sqlite:///:memory: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
 "$interpreter" verification/stage2_ui_offline_pytest.py -q -p no:cacheprovider -p verification.stage1_preservation_plugin \
 tests/test_stage26b_rendered.py tests/test_stage2_profile_journey.py tests/test_family_dashboard_render.py tests/test_mandate_explanation_presentation.py verification/test_ui_session_lifecycle.py \
 --junitxml="$output/journey.xml" | tee "$output/journey.log"
