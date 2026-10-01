-- Independent canonical append-only expectation.
CREATE FUNCTION ah_deny_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'AH history is append-only'; END; $$;

CREATE TRIGGER ah_source_claims_deny_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON ah_source_claims FOR EACH STATEMENT EXECUTE FUNCTION ah_deny_mutation();

CREATE TRIGGER ah_claim_events_deny_mutation BEFORE UPDATE OR DELETE OR TRUNCATE ON ah_claim_events FOR EACH STATEMENT EXECUTE FUNCTION ah_deny_mutation();

