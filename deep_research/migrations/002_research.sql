-- ============================================================
-- Migration: 002_research
-- Description: Deep Research job/report cache tables
-- Date: 2026-07-02
-- ============================================================


CREATE TABLE IF NOT EXISTS research_reports (
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    progress        VARCHAR(100),
    lang            VARCHAR(5)  NOT NULL DEFAULT 'ko',
    report_md       TEXT,
    sections        JSONB,
    sources         JSONB,
    model_version   VARCHAR(200),
    error_message   TEXT,
    requested_by    UUID,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS filings (
    id                SERIAL PRIMARY KEY,
    ticker_id         INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    accession_no      VARCHAR(30) NOT NULL UNIQUE,
    form_type         VARCHAR(10) NOT NULL,
    period_end        DATE,
    section_texts     JSONB,
    section_summaries JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE INDEX IF NOT EXISTS idx_research_ticker_date
    ON research_reports(ticker_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_ticker_completed
    ON research_reports(ticker_id, completed_at DESC)
    WHERE status = 'completed';

CREATE INDEX IF NOT EXISTS idx_research_user_date
    ON research_reports(requested_by, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_research_status_started
    ON research_reports(status, started_at);

CREATE INDEX IF NOT EXISTS idx_filings_ticker
    ON filings(ticker_id, form_type, period_end DESC);


COMMENT ON TABLE research_reports IS
    'Deep Research report jobs and completed Markdown/section JSON cache.';

COMMENT ON TABLE filings IS
    'SEC filing text and summary cache produced by the Deep Research pipeline.';


GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;

