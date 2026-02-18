-- ============================================================
-- Migration: 001_initial_schema
-- Description: 전체 초기 스키마 + ticker_summaries (종합 요약)
-- Date: 2026-02-17
-- ============================================================


-- ── 1. users ──────────────────────────────────────────────────────────────────
-- Supabase Auth UID를 PK로 사용하는 확장 프로필 테이블
CREATE TABLE IF NOT EXISTS users (
    id                  UUID PRIMARY KEY,           -- Supabase Auth UID
    email               VARCHAR(255) NOT NULL UNIQUE,
    display_name        VARCHAR(100),
    preferred_language  VARCHAR(10) NOT NULL DEFAULT 'ko'
                            CHECK (preferred_language IN ('ko', 'en')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 2. tickers ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tickers (
    id          SERIAL PRIMARY KEY,
    symbol      VARCHAR(20) NOT NULL UNIQUE,    -- AAPL, 005930.KS 등
    name        VARCHAR(255) NOT NULL,
    exchange    VARCHAR(50),                    -- NASDAQ, NYSE, KRX 등
    sector      VARCHAR(100),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 3. news_articles ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS news_articles (
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    title           VARCHAR(500) NOT NULL,
    url             TEXT NOT NULL UNIQUE,
    source          VARCHAR(100),               -- Yahoo Finance, MarketWatch 등
    published_at    TIMESTAMPTZ,
    raw_content     TEXT,                       -- 원문 (요약 입력용, 최대 500자 트리밍 후 전달)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ── 4. ticker_summaries ───────────────────────────────────────────────────────
-- [핵심 변경] 기사 단위 개별 요약(news_summaries) 대신
-- 티커 단위 종합 요약을 저장하는 캐시 테이블.
-- 캐시 키: (ticker_id, created_at 기준 24h TTL)
CREATE TABLE IF NOT EXISTS ticker_summaries (
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    article_ids     INTEGER[] NOT NULL DEFAULT '{}',    -- 요약에 사용된 기사 ID 배열
    summary_ko      TEXT,           -- 한국어 bullet 종합 요약 (줄바꿈 구분)
    summary_en      TEXT,           -- 영어 bullet 종합 요약 (줄바꿈 구분)
    sentiment_score DECIMAL(3,2)    CHECK (sentiment_score BETWEEN -1.00 AND 1.00),
    sentiment_label VARCHAR(20)     CHECK (sentiment_label IN ('Positive', 'Neutral', 'Negative')),
    model_version   VARCHAR(50),
    article_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE ticker_summaries IS
    '티커 단위 종합 요약 캐시. 동일 ticker_id 기준 24h TTL로 재사용.';


-- ── 5. guest_rate_limits ──────────────────────────────────────────────────────
-- 비로그인 사용자 IP 기반 일 조회 횟수 제한
CREATE TABLE IF NOT EXISTS guest_rate_limits (
    id      SERIAL PRIMARY KEY,
    ip      VARCHAR(45) NOT NULL,
    date    DATE NOT NULL DEFAULT CURRENT_DATE,
    count   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (ip, date)
);


-- ── 권한 부여 ─────────────────────────────────────────────────────────────────
-- PostgREST(service_role)가 SERIAL 시퀀스에 INSERT할 수 있도록 USAGE 권한 부여
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO service_role;
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;


-- ── 인덱스 ────────────────────────────────────────────────────────────────────
CREATE INDEX idx_news_ticker_date      ON news_articles(ticker_id, published_at DESC);
CREATE INDEX idx_news_url              ON news_articles(url);
CREATE INDEX idx_tickers_symbol        ON tickers(symbol);
CREATE INDEX idx_ticker_summaries_ticker_date
    ON ticker_summaries(ticker_id, created_at DESC);
CREATE INDEX idx_ticker_summaries_ticker_day
    ON ticker_summaries(ticker_id, ((created_at AT TIME ZONE 'UTC' + INTERVAL '9 hours')::DATE));
CREATE INDEX idx_guest_rate_limits_ip_date
    ON guest_rate_limits(ip, date);


-- ── updated_at 자동 갱신 트리거 (users) ──────────────────────────────────────
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
