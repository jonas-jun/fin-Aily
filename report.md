# 심층 리서치 리포트 기능 기획·설계서 (Deep Research v1)

> 미국 주식 AI 분석 서비스 `fin-aily-us`에 **최근 4개 분기 사업보고서(10-K/10-Q)** 와 **최근 8개 분기 컨퍼런스콜 스크립트**를 결합하여 기관투자자급 심층 리서치 리포트를 자동 생성하는 백엔드 기능의 최종 기획서입니다.

## 0. 개발 원칙 — 기존 서비스 무영향(Zero-Impact)

이 기능은 **격리된 백엔드 모듈로 우선 개발**하며, 기능 검증 완료 후 별도 단계로 프론트엔드에 연결합니다.

| 원칙 | 적용 방안 |
|---|---|
| **파일 격리** | 신규 `research_router.py`, `research_service.py`, `research_collector.py` 등을 신설. 기존 [news_router.py](backend/app/routers/news_router.py), [summarization_service.py](backend/app/services/summarization_service.py)는 일체 수정 금지 |
| **DB 격리** | 신규 마이그레이션 `002_ticker_research_reports.sql` 으로 신규 테이블만 추가. 기존 [001_initial_schema.sql](backend/migrations/001_initial_schema.sql) 테이블(`tickers`, `news_articles`, `ticker_summaries`) 스키마 변경 없음 |
| **설정 격리** | `model_config.yaml`에 `research_map`, `research_reduce` 키만 추가. 기존 `market_pulse`, `ticker_brief` 설정은 그대로 유지 |
| **의존성 격리** | 신규 라이브러리(`edgartools` 등)는 별도 그룹으로 [requirements.txt](backend/requirements.txt)에 append만 수행 |
| **라우팅 격리** | 신규 라우터를 `/v1/research/...`로 마운트. 기존 `/v1/news/...`, `/v1/tickers/...` 영향 없음 |
| **프론트 비연결** | 백엔드 단독으로 통합 테스트 통과 → 운영 환경 자체 검증 → 이후 프론트 연결 PR 별도 진행 |

---

## 1. 개요 및 목표

### 1.1 배경
- 현재 `fin-aily-us`는 야후 파이낸스 뉴스 기반 단기 심리 분석(Sentiment Brief) 중심으로, 기업의 펀더멘탈과 중장기 전략 추적에 한계가 있음.
- 1차 출처인 SEC 공시 문서와 어닝스콜 스크립트를 결합하여 정성적·정량적 분석이 융합된 고품질 AI 리서치 탭을 신설.

### 1.2 핵심 목표
1. **무료 데이터 파이프라인**: SEC EDGAR + Motley Fool 무료 아카이브 활용으로 데이터 비용 0원.
2. **대용량 컨텍스트 처리**: 보고서 4개 + 컨콜 8개(수십만 자) 데이터를 계층적 Map-Reduce로 안전 처리.
3. **장기 캐싱 최적화**: 7일 TTL Supabase 캐시로 LLM 비용·외부 요청 부담 최소화.

---

## 2. 시스템 아키텍처

기존 3-Tier 아키텍처(Router → Service → DB Cache)를 그대로 계승하면서 신규 모듈만 추가합니다.

```
[클라이언트] → GET /v1/research/{symbol}
                    │
                    ▼
        [research_router.py]
                    │
        (캐시 확인) ──→ [Supabase: ticker_research_reports] ──(히트 시 즉시 반환)
                    │
            (캐시 미스 시)
                    │
                    ▼
        [research_service.py]  (오케스트레이션)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
[research_collector.py]   [research_pipeline.py]
  ① edgartools           ① Map-Pre : 긴 10-K 섹션 청크 분할 → 부분 요약 머지
     → 10-K / 10-Q 4건   ② Map     : 분기별 마이크로 요약 (병렬 8회)
  ② BS4 스크래퍼          ③ Reduce  : 종합 애널리스트 리포트 (단일 호출)
     → 컨콜 8건
                    │
                    ▼
        [Supabase: ticker_research_reports] 캐시 저장
                    │
                    ▼
                [JSON 응답]
```

---

## 3. 디렉터리 구조 (신규 파일만)

```
backend/
├── app/
│   ├── routers/
│   │   └── research_router.py          # 신규 — /v1/research/{symbol}
│   ├── services/
│   │   ├── research_service.py         # 신규 — 오케스트레이션 (캐시 확인 → 수집 → 분석 → 저장)
│   │   ├── research_collector.py       # 신규 — SEC + Motley Fool 데이터 수집
│   │   ├── research_pipeline.py        # 신규 — 계층적 Map-Reduce LLM 파이프라인
│   │   └── research_cache_service.py   # 신규 — ticker_research_reports CRUD
│   └── model_config.yaml               # 수정 (key 추가만, 기존 key 유지)
├── migrations/
│   └── 002_ticker_research_reports.sql # 신규
├── requirements.txt                    # append만 (edgartools 등)
└── tests/
    └── research/                       # 신규 격리 테스트 디렉터리
        ├── test_collector.py
        ├── test_pipeline.py
        └── test_router_integration.py
```

---

## 4. 데이터 수집 파이프라인

### 4.1 SEC EDGAR (`edgartools`)
- **대상 문서:** 최근 1년 공시 중 `10-K`(연간) + `10-Q`(분기) 총 4건
- **동작:**
  1. 티커 → CIK 매핑 (라이브러리 내장)
  2. `form=["10-K", "10-Q"]` 필터, 최신순 4건 추출
  3. `.text()` 기반 본문 정제 (HTML/태그 제거)
  4. **섹션 단위 파싱**: Item 1A(Risk Factors), Item 7(MD&A), Item 8(Financial Statements & Notes), Item 9(Controls), 부속서(Exhibit) 메타 등으로 구조화하여 별도 슬롯에 저장 — Map-Pre 단계의 청크 분할 기준으로 사용
- **저장 메타:** `form`, `fiscal_year`, `fiscal_quarter`, `filing_date`, `period_of_report`, `doc_id`

### 4.2 Motley Fool 컨퍼런스콜 스크래퍼
- **소스:** `fool.com/earnings/call-transcripts` 무료 공개 아카이브
- **도구:** `requests` + `beautifulsoup4` + `lxml-html-clean` (기존 [requirements.txt](backend/requirements.txt)에 이미 포함)
- **동작:**
  1. 티커별 연도/분기 URL 패턴으로 타겟 생성, 최근 8개 분기 수집
  2. 본문 컨테이너(`class="tailwind-article-body"` 등) 텍스트 추출
  3. CEO/CFO 코멘트와 Q&A 라인 보존
- **저장 메타:** `fiscal_year`, `fiscal_quarter`, `event_date`, `source`, `source_url`

### 4.3 견고성 요구사항
- 4건 중 일부 누락(예: 신규 상장사) 시 가용한 데이터로 fallback 동작.
- 외부 사이트 차단(403/429)에 대비해 `User-Agent` 명시 + 지수 백오프 재시도 3회.
- 수집 단계 실패 시 명확한 에러 코드(`COLLECTOR_SEC_FAILED`, `COLLECTOR_TRANSCRIPT_FAILED`) 반환.

---

## 5. AI 분석 파이프라인 (계층적 Map-Reduce)

원문 크기가 LLM 컨텍스트 윈도우를 초과하거나 'Lost in the Middle' 정보 누락이 발생하기 쉬우므로 **계층적 압축 구조**로 분리합니다.

### 5.0 토큰 예산 설계 (중요)

| 단계 | 입력 토큰(분기당) | 출력 상한 | 비고 |
|---|---|---|---|
| Map-Pre (긴 10-K) | 30K~150K 토큰의 단일 10-K를 섹션 단위로 분할 | 각 섹션당 4K~6K | Item 1A/7/8/9 등 핵심 섹션 위주 청킹, 부속서·반복 헤더 제거 |
| Map (분기별) | 정제된 공시 + 컨콜 ≈ 30K~70K | **16K** | 정량 수치·고유명사 보존, 6섹션 정형 출력 |
| Reduce (종합) | Map 결과 8건 결합 ≈ 80K~130K | **32K** | 10섹션 + 표·8분기 trend 분석 |

> **참고**: Gemini API의 `max_tokens`는 **출력 상한**만 제어합니다. 입력은 모델 컨텍스트 윈도우(Flash 계열 ~1M 토큰)가 한도이며, 이 설계에서는 어떤 단계도 1M을 넘지 않도록 Map-Pre로 미리 압축합니다.

### 5.1 Map-Pre 단계 — 긴 10-K 섹션 청크 분할 후 부분 요약 머지

10-K는 단일 문서가 100K+ 토큰에 달하는 경우가 흔하므로, **Section-Aware Chunking**으로 정보 손실을 최소화합니다.

- **분할 기준:** 수집 단계(4.1)에서 분리해 둔 Item별 섹션을 청크 단위로 사용
- **우선순위(필수 ≥ 보조):**
  1. Item 1A — Risk Factors (필수)
  2. Item 7 — MD&A (필수)
  3. Item 8 — Financial Statements & Notes (필수)
  4. Item 1 — Business Overview (필수)
  5. Item 9A/9B — Controls / Other (보조)
  6. Item 5/6 — Market for Stock / Selected Data (보조)
- **머지 방식:** 각 섹션을 개별 LLM 호출로 4K~6K 요약 생성 → 동일 분기 컨콜과 함께 Map 단계 입력으로 재구성
- **10-Q 처리:** 10-Q는 길이가 짧으므로 Map-Pre를 건너뛰고 Map 단계로 직행

### 5.2 Map 단계 — 분기별 마이크로 요약 (병렬 8회)

각 분기 데이터셋(공시 1건 + 해당 분기 컨콜 1건)을 입력받아 `gemini-3.1-flash-lite`로 정보 누락 없는 압축본 생성. 8개 분기를 `asyncio.gather`로 병렬 호출.

**Map 프롬프트 명세:**
```markdown
당신은 글로벌 상장 기업의 공시 문서와 컨퍼런스콜 스크립트에서
핵심 투자 단서를 추출하는 대용량 금융 데이터 정제 전문가입니다.

대상 티커: {ticker}
대상 분기: {fiscal_year} Q{fiscal_quarter} (또는 FY{fiscal_year} 10-K)

## 추출 가이드라인
1. 구체적 수치(매출액·마진율·금액)와 고유 대명사(고객사·제품명)는 절대 누락/추상화 금지.
2. 가치 판단/추측은 배제, 원문 팩트와 경영진 워딩만 추출.
3. 해당 분기에 언급 없는 항목은 임의 생성 금지 — "해당 분기 언급 없음" 명시.
4. 한국어로 작성, 수치/고유명사/지표는 영문 병기.

## 출력 양식 (마크다운 6섹션 엄수)
### 1. 정량적 재무 실적 및 마진 (Financial Quality)
- 매출/영업이익/순이익 (YoY·QoQ 변화 포함)
- 매출총마진율(GPM), 영업마진율(OPM)
- 영업현금흐름(OCF), 잉여현금흐름(FCF)

### 2. 세그먼트 및 고객 집중도 (Segment & Customers)
- 사업부별/제품군별 매출 또는 비중
- 주요 고객사(Major Customers) 의존도 및 리스크 코멘트

### 3. 경영진 가이던스 및 핵심 가정 (Management Guidance)
- 다음 분기/연간 매출·EPS·마진율 전망
- 가이던스의 전제 가정(시장 환경, 수요 예측 등)

### 4. 자본 배분 및 투자 현황 (Capital Allocation)
- 자사주 매입, 배당, CapEx, M&A, 부채 상환

### 5. 공시 문구 및 리스크 팩터 변화 (Filing Delta)
- 이전 분기 대비 신규/강화된 리스크 요인
- 회계 정책 및 세그먼트 보고 방식 변화

### 6. 내러티브 및 핵심 키워드 (Narrative & Tone)
- 반복 강조 키워드/전략 방향 (AI 포지셔닝, 비용 절감 등)
- Q&A에서의 자신감 변화, 우선순위 변동
```

### 5.3 Reduce 단계 — 종합 애널리스트 리포트 (단일 호출)

8개 분기 마이크로 요약을 시간 순서로 결합 → 분석 프롬프트 주입 → 최종 한국어 마크다운 리포트 생성.

**Reduce 프롬프트 명세:**
```markdown
당신은 미국 상장 기업 전문 기관투자자급 주식 리서치 애널리스트입니다.
제공된 [공시 문서(10-K/10-Q 요약)]와 [최근 8개 분기 컨퍼런스콜 요약]만을
바탕으로 외부 데이터 없이 1차 출처에 기반한 심층 투자 리포트를 한국어로 작성하라.

[기업명] {company_name} / [티커] {ticker}

## 데이터 원칙
1. 분석 근거는 오직 제공된 요약 데이터에 한정.
2. 수치는 제공 데이터에 명시된 검증 가능한 숫자만 인용.
3. 데이터에 없는 사항은 임의 추정 금지, "제공된 공시/컨콜 내 확인 불가" 명시.
4. 다음을 명확히 구분:
   - 확인된 과거 사실 (Historical Fact)
   - 경영진 가이던스 및 전망 (Management Guidance)
   - 분석가의 객관적 해석 (Analytical Interpretation)

## 보고서 구성
1. 투자 요약 (Investment Summary)
2. 사업 구조 및 세그먼트 분석
3. 재무 품질 및 마진 분석
4. 고객 및 매출 집중도 분석
5. 컨퍼런스콜 경영진 가이던스 분석
6. 핵심 리스크 (Risk Factors)
7. 공시 변화 분석 (Filing Delta)
8. 내러티브 변화 추적 (최근 8개 컨퍼런스콜 기준)
9. 자본 배분 품질 분석 (Capital Allocation)
10. 최종 종합 평가

## 작성 지침
- 모든 섹션에서 단순 수치 나열이 아닌 '시간에 따른 변화(Trend)' 중심으로 분석.
- 수치 비교, 세그먼트 분석은 표(Table) 적극 활용.
- 출처를 명시 (예: "FY2025 10-Q 기준", "2024년 4분기 어닝스콜").
- 범용 산업 설명 배제, 이 기업 고유 데이터·인사이트에만 집중.
- 한국어 작성. 고유명사·지표명·수치는 영문 병기 가능.
```

### 5.4 모델 설정 (model_config.yaml 추가분)
기존 키는 그대로 두고 아래 키만 추가합니다.

```yaml
cache:
  # 기존 키 유지
  research_ttl_hours: 168     # 7일 (신규)

features:
  # 기존 market_pulse, ticker_brief 유지
  research_map_pre:
    model: gemini-3.1-flash-lite
    max_tokens: 6144           # 긴 10-K 섹션 청크당 부분 요약
  research_map:
    model: gemini-3.1-flash-lite
    max_tokens: 16384          # 분기별 마이크로 요약 (수치·고유명사 보존)
  research_reduce:
    model: gemini-3.1-flash-lite
    max_tokens: 32768          # 10섹션 종합 리포트 (표·8분기 trend 포함)
```

> Gemini Flash-Lite의 실제 출력 토큰 상한이 모델 버전에 따라 다를 수 있어, Phase 2 검증 단계에서 finish_reason="MAX_TOKENS" 발생 빈도를 모니터링하고 필요 시 모델을 `gemini-3.1-flash` 또는 `gemini-3.1-pro`로 승격합니다.

---

## 6. 데이터베이스 스키마

### 6.1 신규 마이그레이션: `002_ticker_research_reports.sql`

```sql
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
```

### 6.2 `source_metadata` JSONB 규격

```json
{
  "ticker": "ICHR",
  "analysis_period": "최근 4개 분기 공시 & 최근 8개 분기 컨퍼런스콜",
  "sources": {
    "sec_filings": [
      {
        "form": "10-Q",
        "fiscal_year": 2025,
        "fiscal_quarter": 3,
        "filing_date": "2025-11-05",
        "period_of_report": "2025-09-30",
        "doc_id": "0001564590-25-004321"
      }
    ],
    "earning_calls": [
      {
        "fiscal_year": 2026,
        "fiscal_quarter": 1,
        "event_date": "2026-04-28",
        "source": "Motley Fool",
        "source_url": "https://www.fool.com/earnings/call-transcripts/..."
      }
    ]
  }
}
```

---

## 7. API 엔드포인트 명세

신규 라우터 [research_router.py](backend/app/routers/research_router.py)를 신설하고 `/v1` 프리픽스 하위에 마운트합니다. [main.py](backend/app/main.py)에는 `app.include_router(research_router.router, prefix=PREFIX)` 한 줄만 추가.

### `GET /v1/research/{symbol}`

| 항목 | 값 |
|---|---|
| 설명 | 종목의 심층 AI 투자 리포트 조회 (7일 캐시) |
| Path | `symbol` (예: `ICHR`, `NVDA`) |
| Query | `force_refresh: bool` (default `false`) — `true`면 캐시 무효화 후 재생성 |
| Rate Limit | 기존 [RateLimitMiddleware](backend/app/middleware/rate_limit_middleware.py) 적용. 단, 리포트 생성은 비용·시간 부담이 크므로 별도 분당 5회 제한 권장 |

**성공 응답 (200 OK):**
```json
{
  "symbol": "ICHR",
  "company_name": "Ichor Holdings, Ltd.",
  "generated_at": "2026-05-17T11:00:00Z",
  "model_version": "gemini-3.1-flash-lite",
  "report_markdown": "# 심층 투자 리포트\n\n## 1. 투자 요약...",
  "source_metadata": { "...": "..." }
}
```

**에러 응답:**
| 코드 | 의미 |
|---|---|
| `404 NO_TICKER` | 티커를 식별할 수 없음 |
| `503 COLLECTOR_SEC_FAILED` | EDGAR 수집 실패 |
| `503 COLLECTOR_TRANSCRIPT_FAILED` | 컨콜 스크래핑 실패 |
| `503 ANALYSIS_FAILED` | LLM 분석 단계 실패 |
| `429 RATE_LIMITED` | 분당 호출 제한 초과 |

---

## 8. 단계별 구현 로드맵

각 단계 종료 시 **격리된 단위 테스트로 검증**한 뒤 다음 단계로 이동합니다. 모든 단계가 통과한 뒤 마지막에 프론트엔드 연결을 별도 PR로 진행합니다.

### Phase 1 — 데이터 수집기 (research_collector.py)
- [ ] `edgartools` 추가, 단일 티커에 대해 10-K/10-Q 4건을 본문 정제까지 수행
- [ ] 10-K **Item 단위 섹션 파싱** 결과를 별도 필드로 보존 (Map-Pre 입력용)
- [ ] Motley Fool 컨콜 스크래퍼: 8개 분기 URL 생성 → 본문 추출 → 정제
- [ ] 누락/실패 케이스 fallback 처리, 재시도 로직
- [ ] **검증:** `tests/research/test_collector.py` — `ICHR`, `NVDA`, `AAPL` 3종에 대해 정상 수집 확인

### Phase 2 — Map-Reduce 파이프라인 (research_pipeline.py)
- [ ] Map-Pre: 긴 10-K 섹션 청크 분할 → 부분 요약 → 머지 로직
- [ ] Map: 분기별 요약 8건 병렬 생성 (`asyncio.gather`)
- [ ] Reduce: 종합 리포트 단일 생성
- [ ] 토큰 카운트 측정, `finish_reason="MAX_TOKENS"` 발생 시 경고 로깅 및 모델 승격 fallback
- [ ] **검증:** 더미/실수집 데이터로 종단 LLM 호출 → 마크다운 6/10 섹션 구조 충족 확인

### Phase 3 — DB 마이그레이션 & 캐시 (research_cache_service.py)
- [ ] `002_ticker_research_reports.sql` 적용
- [ ] `get_cached_report`, `save_report`, `invalidate_report` 3종 CRUD 구현
- [ ] **검증:** 동일 티커 7일 내 재요청 시 캐시 히트 확인

### Phase 4 — 라우터 통합 (research_router.py)
- [ ] `/v1/research/{symbol}` 엔드포인트 노출
- [ ] [main.py](backend/app/main.py)에 라우터 1줄 추가 — **기존 라우터 영향 없음 재확인**
- [ ] 별도 분당 5회 Rate Limit 적용
- [ ] **검증:** `tests/research/test_router_integration.py` — `httpx`로 종단 호출, 캐시 히트/미스 양쪽 시나리오 통과

### Phase 5 — 운영 환경 자체 검증
- [ ] 스테이징/로컬에서 5~10개 티커 실호출, 응답 시간·토큰·리포트 품질 점검
- [ ] 기존 `/v1/news/...`, `/v1/tickers/...` 회귀 테스트 통과 확인
- [ ] 비용 추정 후 필요 시 모델/캐시 TTL/토큰 상한 튜닝

### Phase 6 — 프론트엔드 연결 (별도 PR)
- 위 5단계가 모두 통과한 뒤에만 진행. 본 기획서 범위에서는 백엔드 한정.

---

## 9. 비용·성능 예상치 (참고용)

| 항목 | 예상 |
|---|---|
| 1회 리포트 생성 입력 토큰 | Map-Pre ~150K(연 1회 10-K 한정) + Map 8회 × 50K + Reduce ~120K ≈ 600K~700K |
| 1회 리포트 생성 출력 토큰 | Map-Pre ~30K + Map 8회 × 12K + Reduce ~25K ≈ 150K |
| 1회 생성 시간 | 60~120초 (Map 병렬 + Reduce 직렬) |
| 캐시 히트율 목표 | 동일 티커 주간 재요청 시 ≥ 90% |
| 1티커 7일 평균 비용 | LLM 비용만 발생, 데이터 수집 비용 0원 |

---

## 10. 리스크 및 완화

| 리스크 | 완화 방안 |
|---|---|
| Motley Fool 차단/구조 변경 | User-Agent 명시, 백오프 재시도, 파서 변경 대비 어댑터 패턴, 대체 소스(seekingalpha 공개 미리보기) 추후 검토 |
| SEC EDGAR rate limit | `edgartools` 내장 throttle 사용 + 7일 캐시로 호출 빈도 억제 |
| LLM 출력 토큰 한계 도달 | `finish_reason="MAX_TOKENS"` 모니터링 → 모델 승격(Flash → Pro) 또는 섹션 분할 추가 |
| 잘못된 정보 생성(할루시네이션) | 프롬프트 내 "확인 불가 명시" 원칙 + 사용된 source_metadata 응답에 동봉하여 추적성 확보 |
| 기존 서비스 영향 | Phase 5 회귀 테스트 통과 전 프로덕션 배포 금지 |

---

본 기획서를 기준으로 Phase 1부터 순차 구현하면 기존 서비스에 영향을 주지 않으면서 격리된 환경에서 안전하게 심층 리서치 기능을 검증·도입할 수 있습니다.
