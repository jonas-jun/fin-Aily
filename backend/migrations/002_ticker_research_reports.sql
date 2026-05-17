-- ============================================================
-- Migration: 002_ticker_research_reports
-- Description: 심층 리서치 리포트 캐시 테이블 (7일 TTL)
-- ============================================================

CREATE TABLE IF NOT EXISTS ticker_research_reports (
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    report_markdown TEXT NOT NULL,                  -- 최종 한국어 마크다운 리포트
    source_metadata JSONB NOT NULL,                 -- 분석에 사용된 1차 출처 추적
    model_version   VARCHAR(50) NOT NULL,           -- 사용 LLM 모델명
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_research_reports_ticker_date
    ON ticker_research_reports(ticker_id, created_at DESC);

COMMENT ON TABLE ticker_research_reports IS
    '티커별 공시+컨콜 기반 심층 AI 투자 리포트 캐시. 7일 TTL.';

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
