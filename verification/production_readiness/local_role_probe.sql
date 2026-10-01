-- Explicit fixture-only enabled state, AFTER dark migration catalogue comparison.
GRANT SELECT ON ah_source_claims,ah_claim_events TO ah_ci_reader,ah_ci_importer;
GRANT INSERT ON ah_source_claims,ah_claim_events TO ah_ci_importer;
GRANT USAGE ON SEQUENCE ah_source_claims_id_seq,ah_claim_events_id_seq TO ah_ci_importer;
GRANT INSERT ON documents TO ah_ci_registrar;
CREATE POLICY fixture_claim_read ON ah_source_claims FOR SELECT TO ah_ci_reader,ah_ci_importer USING (site_id=1 AND scheme_application_id=1);
CREATE POLICY fixture_claim_append ON ah_source_claims FOR INSERT TO ah_ci_importer WITH CHECK (site_id=1 AND application_id=1 AND scheme_application_id=1 AND document_id=1 AND origin_kind='reviewed_import');
CREATE POLICY fixture_event_read ON ah_claim_events FOR SELECT TO ah_ci_reader,ah_ci_importer USING (EXISTS(SELECT 1 FROM ah_source_claims c WHERE c.id=claim_id));
CREATE POLICY fixture_event_append ON ah_claim_events FOR INSERT TO ah_ci_importer WITH CHECK (EXISTS(SELECT 1 FROM ah_source_claims c WHERE c.id=claim_id));
