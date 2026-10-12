-- Console human authoring only. No provider, source, catalog or publish-job writes.
-- Existing SELECT and revocation rights from 0008 cover invoker-rights triggers:
-- publication UPDATE, change_match.status UPDATE and weekly_top DELETE.
GRANT INSERT (kind, url, title, excerpt, observed_at) ON core.evidence TO bb_api;
GRANT UPDATE (title) ON core.evidence TO bb_api;
GRANT INSERT, DELETE ON core.x_evidence TO bb_api;
GRANT INSERT (idea_id, item, result, query_fields, detail) ON core.trace_check TO bb_api;
GRANT UPDATE (result, detail, checked_at) ON core.trace_check TO bb_api;
GRANT INSERT (idea_id, status, profile_version, external_search) ON core.trace_verdict TO bb_api;
GRANT UPDATE (status, profile_version, external_search, decided_at) ON core.trace_verdict TO bb_api;
GRANT INSERT (idea_id, "primary", secondary, rationale, extractor, model, decided_by)
    ON core.diagnosis TO bb_api;
GRANT UPDATE ("primary", secondary, rationale, extractor, model, decided_by, decided_at)
    ON core.diagnosis TO bb_api;
GRANT INSERT (change_id, idea_id, llm_verdict, what_changed, how_now, model, prompt_version, status)
    ON core.change_match TO bb_api;
GRANT UPDATE (llm_verdict, what_changed, how_now, model, prompt_version, status)
    ON core.change_match TO bb_api;
GRANT INSERT (idea_id, as_of, tech, data, regulation, policy, weights, n_scored, s,
              verdict, resolve_condition, scored_by) ON core.timeliness TO bb_api;
GRANT UPDATE (tech, data, regulation, policy, weights, n_scored, s, verdict,
              resolve_condition, scored_by, created_at) ON core.timeliness TO bb_api;
GRANT USAGE ON SEQUENCE core.evidence_id_seq, core.change_match_id_seq TO bb_api;

-- Trace is review material too: reverting a changed trace must never restore an
-- earlier approval. Timestamp-only refreshes and identical upserts are harmless.
CREATE FUNCTION core.revoke_on_trace_change() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
    r := CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    IF TG_TABLE_NAME IN ('trace_check', 'trace_verdict') THEN
        PERFORM core.revoke_idea(r.idea_id);
    ELSIF TG_TABLE_NAME = 'x_evidence' THEN
        IF r.target_type = 'trace' THEN
            PERFORM core.revoke_idea(split_part(r.target_id, ':', 1));
        END IF;
    END IF;
    RETURN NULL;
END $$;

CREATE TRIGGER trace_check_revoke_insert_delete AFTER INSERT OR DELETE ON core.trace_check
    FOR EACH ROW EXECUTE FUNCTION core.revoke_on_trace_change();
CREATE TRIGGER trace_check_revoke_update AFTER UPDATE ON core.trace_check FOR EACH ROW
    WHEN (ROW(OLD.result, OLD.detail) IS DISTINCT FROM ROW(NEW.result, NEW.detail))
    EXECUTE FUNCTION core.revoke_on_trace_change();
CREATE TRIGGER trace_verdict_revoke_insert_delete AFTER INSERT OR DELETE ON core.trace_verdict
    FOR EACH ROW EXECUTE FUNCTION core.revoke_on_trace_change();
CREATE TRIGGER trace_verdict_revoke_update AFTER UPDATE ON core.trace_verdict FOR EACH ROW
    WHEN (ROW(OLD.status, OLD.profile_version, OLD.external_search)
          IS DISTINCT FROM ROW(NEW.status, NEW.profile_version, NEW.external_search))
    EXECUTE FUNCTION core.revoke_on_trace_change();
CREATE TRIGGER trace_evidence_link_revoke AFTER INSERT OR DELETE ON core.x_evidence FOR EACH ROW
    EXECUTE FUNCTION core.revoke_on_trace_change();
