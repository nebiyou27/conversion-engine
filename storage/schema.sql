-- Conversion Engine storage schema. One table per epistemic layer.
-- Append-only semantics enforced by the Python API (no update/delete paths).

CREATE TABLE IF NOT EXISTS evidence (
    evidence_id   TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL,
    fact          TEXT NOT NULL,
    source_url    TEXT NOT NULL,
    source_type   TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL,
    method        TEXT NOT NULL,
    raw_payload   TEXT
);
CREATE INDEX IF NOT EXISTS idx_evidence_company ON evidence(company_id);

CREATE TABLE IF NOT EXISTS claims (
    claim_id      TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL,
    kind          TEXT NOT NULL
                  CHECK(kind IN ('funding_round','hiring_surge','leadership_change','layoff_event','company_metadata')),
    assertion     TEXT NOT NULL,
    tier          TEXT NOT NULL
                  CHECK(tier IN ('verified','corroborated','inferred','below_threshold')),
    built_at      TEXT NOT NULL,
    evidence_ids  TEXT NOT NULL,
    payload       TEXT
);
CREATE INDEX IF NOT EXISTS idx_claims_company ON claims(company_id);
CREATE INDEX IF NOT EXISTS idx_claims_tier    ON claims(tier);
CREATE INDEX IF NOT EXISTS idx_claims_kind    ON claims(kind);

CREATE TABLE IF NOT EXISTS judgments (
    judgment_id   TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL,
    kind          TEXT NOT NULL
                  CHECK(kind IN ('icp','segment','ai_maturity','competitor_gap')),
    value         TEXT NOT NULL,
    rationale     TEXT,
    claim_ids     TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judgments_company ON judgments(company_id);

CREATE TABLE IF NOT EXISTS drafts (
    draft_id      TEXT PRIMARY KEY,
    company_id    TEXT NOT NULL,
    contact_id    TEXT,
    channel       TEXT NOT NULL CHECK(channel IN ('email','sms')),
    path          TEXT NOT NULL CHECK(path IN ('ack','commitment')),
    subject       TEXT,
    body          TEXT NOT NULL,
    claim_ids     TEXT NOT NULL,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_drafts_company ON drafts(company_id);

CREATE TABLE IF NOT EXISTS gate_reports (
    report_id     TEXT PRIMARY KEY,
    draft_id      TEXT NOT NULL,
    citation_ok   INTEGER NOT NULL CHECK(citation_ok  IN (0,1)),
    shadow_ok     INTEGER NOT NULL CHECK(shadow_ok    IN (0,1)),
    forbidden_ok  INTEGER NOT NULL CHECK(forbidden_ok IN (0,1)),
    failures      TEXT,
    decision      TEXT NOT NULL CHECK(decision IN ('pass','human_queue')),
    created_at    TEXT NOT NULL,
    FOREIGN KEY(draft_id) REFERENCES drafts(draft_id)
);
CREATE INDEX IF NOT EXISTS idx_gate_reports_draft ON gate_reports(draft_id);
