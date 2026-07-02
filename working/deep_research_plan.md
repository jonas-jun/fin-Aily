# Deep Research (심층 리서치) 기능 기획서

> 이 문서 한 장으로 구현 가능하도록 아키텍처·API·DB 스키마·**전체 프롬프트 세트**를 모두 포함한다.
> 원본 프롬프트(`prompt.txt`)의 10개 섹션 지시는 5장의 섹션별 프롬프트로 분해·이관되었다.

## 1. 개요

티커를 입력하면 API로 수집한 1차 데이터(SEC 공시, XBRL 재무, 컨센서스, 주가)를 섹션별로 flash급 모델에
나눠 처리한 뒤, 10개 섹션(Executive Summary ~ Variant Perception)의 한국어 심층 리포트를 조립해 반환한다.

**개발 전략: 백엔드 단독 선행 → 이후 프론트 연동**

| 단계 | 내용 | 기존 서비스 영향 |
|---|---|---|
| Stage 1 | CLI 파이프라인 — 서버 없이 티커 → `.md` 리포트 생성 | 없음 (신규 `research-backend/`) |
| Stage 2 | 독립 API 서버 — 잡 생성/폴링 API + DB 캐시, 별도 Cloud Run 배포 | DB 테이블 추가만 |
| Stage 3 | 본 서비스 연동 — 프론트 탭 + 인증/사용량 제한 | 프론트 3파일 + env |
| Stage 4 | 고도화 — 트랜스크립트 API, 히스토리, 자동 갱신 | 기능 단위 진행 |

**핵심 아키텍처 결정 3가지**

1. **API 기반 데이터 수집**: 모델 검색(grounding)에 의존하지 않고 EDGAR·yfinance API로 데이터를 직접 수집해 주입. 재무 수치는 LLM이 아닌 코드로 계산 → 환각 원천 차단.
2. **섹션별 flash 병렬 생성**: 10개 섹션을 각각 독립된 flash 호출로 생성. pro 1회 대비 저렴하고, 병렬 실행으로 빠르며, 섹션당 컨텍스트가 작아 품질이 안정적.
3. **형식은 코드가 소유**: 모델은 구조화 출력(JSON)으로 "내용"만 채우고, 문서 구조(헤딩·표·목차·출처)는 코드의 렌더러가 결정 → 형식 일관성을 프롬프트 준수에 맡기지 않음.

---

## 2. 필요한 API 정리

### 2-1. 외부 데이터 API

| API | 용도 | 주요 엔드포인트 | 인증/제한 | 비용 |
|---|---|---|---|---|
| **SEC EDGAR — Ticker↔CIK 매핑** | 티커를 CIK로 변환 (모든 EDGAR 호출의 선행 단계) | `https://www.sec.gov/files/company_tickers.json` | User-Agent 헤더 필수 | 무료 |
| **SEC EDGAR — Submissions** | 공시 목록 (최근 4년 10-K/10-Q/8-K/20-F) | `https://data.sec.gov/submissions/CIK{cik:010d}.json` | User-Agent 필수, **10 req/s** | 무료 |
| **SEC EDGAR — Company Facts (XBRL)** | 재무 시계열 원천: 매출·이익·FCF 구성·SBC·R&D·Capex·자사주·배당·부채·주식수 | `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json` | 동일 | 무료 |
| **SEC EDGAR — 공시 원문** | 10-K/10-Q 텍스트(Item 1/1A/7), 8-K 실적 보도자료 | `https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}` | 동일 | 무료 |
| **yfinance** (비공식, 기존 의존성) | 컨센서스, 목표주가, forward 멀티플, 피어 지표, 주가 히스토리 | `Ticker().info` / `.earnings_estimate` / `.analyst_price_targets` / `.history()` | 비공식 — 과호출 시 차단 위험 | 무료 |
| **Gemini API** (기존 사용, `google-genai`) | 섹션 생성(flash, `response_schema`), 공시 사전 요약(flash-lite) | `client.aio.models.generate_content` | `GEMINI_API_KEY` | 유료 — 리포트 1건 ≈ 섹션 10회 + 사전요약 ~10회 + 검수 1회 |

### 2-2. 선택 API (Stage 4 — 섹션 5·7 보강)

| API | 용도 | 비고 |
|---|---|---|
| FMP (Financial Modeling Prep) | 어닝스콜 트랜스크립트(8분기), 피어 리스트 | 유료 |
| API Ninjas — Earnings Transcript | 트랜스크립트 대안 | 저가 플랜 |
| Finnhub | 피어 그룹, 추정치 보강 | 무료 티어 제한적 |

> Stage 1~3은 유료 데이터 API 없이 진행: 섹션 7은 8-K 실적 보도자료로, 섹션 5는 yfinance 피어 지표 + 10-K 경쟁 서술로 대체.

### 2-3. 리서치 백엔드가 제공할 API (Stage 2)

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/v1/research/{symbol}` | 잡 시작. TTL 내 완료본 있으면 즉시 반환(`cached: true`), 진행 중 잡 있으면 해당 잡 ID 반환 |
| `GET` | `/v1/research/{symbol}` | 최신 완료 리포트 조회 (없으면 404) |
| `GET` | `/v1/research/jobs/{job_id}` | 잡 폴링: `{status, progress, report?, error?}` |
| `GET` | `/health` | 헬스체크 |

---

## 3. 파이프라인 아키텍처

```
[잡 시작]
   │
   ▼
① 데이터 수집 (병렬)                          ② 팩트팩 구성 (코드)
   EDGAR 공시 텍스트 ─┐                          - 5년 재무 시계열 표 (XBRL 계산)
   XBRL companyfacts ─┼─► 정규화/캐시 ──────►     - 밸류에이션 지표 표
   yfinance 컨센서스 ─┤                          - 회사 기본 정보
   yfinance 주가     ─┘                          → 모든 섹션 호출에 공통 주입
   │
   ▼
③ 사전 요약 Map (flash-lite, 병렬): 10-K Item 1/1A/7, 8-K 원문 → 요약 (프롬프트 P-MAP)
   │
   ▼
④ Wave 1: 섹션 2~9 병렬 생성 (flash × 8, 프롬프트 P-02 ~ P-09)
   각 호출 = 스타일 가이드(P-SYS) + 팩트팩 + 섹션 전용 데이터 + response_schema
   │
   ▼
⑤ Wave 2: 섹션 1 + 10 생성 (flash × 2, 프롬프트 P-01, P-10)
   Wave 1의 key_takeaway 모음을 입력으로 → 전체를 관통하는 결론
   │
   ▼
⑥ 조립 (코드, LLM 없음): 헤더 + 목차 + 섹션 렌더링 + 수치 표 삽입 + 출처 목록
   │
   ▼
⑦ (선택) 검수 패스 (flash × 1, 프롬프트 P-QA): 섹션 간 모순 점검 (로깅용)
```

- Wave 1은 `asyncio.gather` 병렬 실행 → 전체 소요 시간 ≈ 가장 느린 섹션 1개 + Wave 2
- 섹션 1·10은 다른 섹션 결론에 의존하므로 Wave 분리 — Executive Summary를 마지막에 쓰는 실제 애널리스트 워크플로와 동일
- 섹션 부분 실패 허용: 실패 섹션만 "생성 실패" 표기하고 리포트는 완성

### 소스 → 섹션 매핑

| # | 섹션 | 주입 데이터 | 소스 | 프롬프트 |
|---|---|---|---|---|
| 2 | Business Structure & Narrative Shift | 세그먼트 매출표, Item 1·MD&A 요약(4년) | EDGAR + XBRL | P-02 |
| 3 | Financial Quality & Margin | 5년 재무 시계열 표 | XBRL | P-03 |
| 4 | Filing Delta & QoE | Risk Factors 요약(연도별), 발생액 지표 | EDGAR + XBRL | P-04 |
| 5 | Competitive Landscape | 피어 비교표, 10-K 경쟁 서술 | yfinance + EDGAR | P-05 |
| 6 | Capital Allocation | 자본 배분 시계열 (자사주/배당/부채/M&A) | XBRL | P-06 |
| 7 | Earnings Call & Guidance | 8-K 실적 보도자료 요약(8분기) | EDGAR | P-07 |
| 8 | Analyst Consensus & Valuation | 컨센서스·밸류에이션 표 | yfinance | P-08 |
| 9 | Technical & Key Risks | 기술적 지표 표 (MA·상대강도 등) | yfinance | P-09 |
| 1 | Executive Summary | Wave 1 key_takeaway 모음 | Wave 1 출력 | P-01 |
| 10 | Variant Perception & Final Assessment | Wave 1 key_takeaway + 팩트팩 | Wave 1 출력 | P-10 |

---

## 4. 형식 일관성 보장 전략

1. **구조화 출력**: 모든 섹션 호출에 `response_schema`(JSON 강제) → 모델이 Markdown을 직접 쓰지 않음. 렌더링(헤딩·표·순서)은 코드가 담당. 수치 표는 XBRL에서 코드로 생성해 삽입하고, 모델은 표를 "해석"만 함.
2. **공통 스타일 가이드**: 전 호출에 동일 system instruction(P-SYS) 주입 — 문체·수치 표기·판단 구분 규칙 통일.
3. **공통 팩트팩**: 핵심 수치 표 1벌을 모든 섹션에 동일 주입 → 섹션 간 수치 모순 방지 (single source of truth).
4. **검수 패스**: 조립 후 P-QA 1회로 모순·불일치 로깅 (수정하지 않음 — 프롬프트 개선에 활용).

**공통 출력 스키마 베이스** (모든 섹션 스키마가 상속):

```python
class SectionBase(BaseModel):
    key_takeaway: str          # 섹션 결론 1문장 — Wave 2 입력 + 렌더링 시 섹션 첫 줄 강조
    data_gaps: list[str] = []  # 제공 데이터로 확인 불가했던 항목 — 렌더링 시 섹션 말미 각주
```

---

## 5. 프롬프트 세트

> 파일 위치: `research-backend/app/prompts/`. 플레이스홀더는 `{변수}` 표기.
> 모든 섹션 호출 = **system**: P-SYS + **user**: 해당 섹션 프롬프트 + **response_schema**: 섹션 스키마.

### P-SYS — 공통 스타일 가이드 (`style_guide.txt`, system instruction)

```
당신은 미국 상장기업을 전문으로 하는 최고 수준의 기관투자자용 주식 리서치 애널리스트입니다.
지금부터 {company_name}({ticker})에 대한 심층 리서치 리포트의 한 섹션을 작성합니다.

[데이터 규칙 — 절대 준수]
1. 분석은 반드시 함께 제공된 데이터(팩트팩, 섹션 데이터)에만 근거해야 합니다.
2. 데이터를 지어내거나 추정하지 마세요. 제공된 데이터로 확인할 수 없는 수치·사실은 본문에
   쓰지 말고 data_gaps 필드에 "확인 불가: <항목>" 형식으로 기록하세요.
3. 모든 수치는 팩트팩의 값을 그대로 사용하세요. 임의 재계산·반올림 변경 금지.
4. 정적 서술보다 시간에 따른 변화(추세, 변곡점, 가속/감속)를 중심으로 분석하세요.
5. 서술 시 다음 네 가지를 명확히 구분하세요:
   [사실] 공시·재무제표에서 확인된 역사적 사실
   [가이던스] 경영진이 제시한 전망
   [컨센서스] 애널리스트 추정치
   [해석] 당신의 분석적 판단
   → 문장 앞에 태그를 붙이지 말고, "~로 공시했다 / 경영진은 ~를 제시했다 /
     컨센서스는 ~이다 / ~로 판단된다" 처럼 문형으로 구분하세요.

[문체 규칙]
- 한국어 보고서체 (예: "~했다", "~로 판단된다"). 경어체("~합니다") 금지.
- 회사명: 처음 등장 시 "{company_name}({ticker})", 이후 "{company_name}" 또는 "동사".
- 금액: $10억 이상 "$12.3B", 미만 "$456M". 비율: 소수점 1자리 "23.4%". 배수: "12.3x".
- 회계연도 "FY2025", 분기 "FY25 Q3" 형식.
- 전문 용어는 처음만 한국어(영문 병기) — 예: "자사주 매입(buyback)" — 이후 한국어만.
- "상당히", "꽤" 같은 모호한 표현 대신 데이터에 근거한 구체적 서술.

[출력 규칙]
- 지정된 JSON 스키마로만 출력합니다. 필드 값 안에 Markdown 문법(##, **, |표|)을 쓰지 마세요.
  문서 서식은 시스템이 처리합니다.
- key_takeaway: 이 섹션의 결론을 한 문장으로 압축. Executive Summary 작성의 입력으로 사용됩니다.
```

### P-MAP — 공시 사전 요약 (`map_filing.txt`, flash-lite)

```
다음은 {company_name}({ticker})의 {form_type} ({period}) 공시 중 "{item_name}" 부분의 원문입니다.
이후 리서치 분석 단계에서 사용할 요약을 작성하세요.

1. 사업 구조, 전략 우선순위, 리스크, 구체적 수치 언급 등 분석 가치가 있는 내용을 빠짐없이 포함
2. 원문에 없는 내용을 추가하지 말 것
3. 경영진이 강조한 키워드와 새로 등장한 주제·표현을 그대로 보존할 것 (내러티브 변화 추적에 사용됨)
4. 한국어 불렛 15개 이내. 각 불렛은 완결된 문장으로.

[원문]
{filing_text}
```

### P-02 — 사업 구조 및 내러티브 변화 (Wave 1)

```
# 과업: 섹션 2 — 사업 구조 및 내러티브 변화 분석 (최근 4년)

아래 데이터를 근거로 분석하세요.

1. 세그먼트별·지역별 매출 구성이 4년간 어떻게 변했는가 (증감 방향, 변곡점, 믹스 변화의 의미)
2. 최근 인수·매각이 사업 구조에 미친 영향 (데이터에 나타난 범위에서)
3. 연도별 공시 요약을 비교해 경영진 내러티브의 변화를 추적:
   - 새로 강조되기 시작한 키워드·주제 (특히 AI 관련 포지셔닝 변화)
   - 사라지거나 축소된 우선순위
   - 전략적 피벗 신호
4. 구조적으로 중요도가 커지는 세그먼트와 약해지는 세그먼트를 판별

[출력 필드]
- key_takeaway / data_gaps (공통)
- segment_shift_analysis: list[str] — 세그먼트·지역 믹스 변화 분석 문단들
- narrative_shifts: list — 각 항목 {theme: 주제, direction: "신규 등장"|"강조 확대"|"축소"|"소멸",
  evidence: 근거가 된 연도와 표현, implication: 해석}
- rising_segments: list — {segment, rationale}
- weakening_segments: list — {segment, rationale}

[데이터]
## 팩트팩
{factpack}
## 세그먼트 매출 시계열 (코드 계산)
{segment_table}
## 연도별 10-K 사업 개요(Item 1) 요약
{item1_summaries}
## 연도별 MD&A(Item 7) 요약
{mdna_summaries}
```

### P-03 — 재무 퀄리티 및 마진 (Wave 1)

```
# 과업: 섹션 3 — 재무 퀄리티 및 마진 분석 (최근 5년)

팩트팩의 5년 재무 시계열을 근거로 분석하세요. 수치 나열이 아니라
"왜 그렇게 움직였고, 앞으로 유지될 수 있는가"를 설명하는 것이 목적입니다.

1. 매출 성장률, GPM/OPM/NPM, FCF 마진, ROIC, SBC 비중, R&D 집약도, Capex 집약도의 추세 해석
2. 마진 확장 동인과 마진 압축 리스크 판별
3. 영업 레버리지(매출 증가분이 이익으로 확대되는 구조) 존재 여부와 근거
4. 수익성 개선(또는 악화)이 구조적 / 경기순환적 / 회계적 / 믹스 효과 중 무엇에 기인하는지 판정

[출력 필드]
- key_takeaway / data_gaps (공통)
- trend_analysis: list — {heading: 지표 그룹명, paragraphs: list[str]}
- margin_drivers: list[str] — 확장 동인
- margin_risks: list[str] — 압축 리스크
- operating_leverage_assessment: str — 판단 + 근거
- sustainability_verdict: {classification: "구조적"|"순환적"|"회계적"|"믹스", rationale: str}

[데이터]
## 팩트팩
{factpack}
```

### P-04 — 공시 변화(Delta) 및 이익의 질 (Wave 1)

```
# 과업: 섹션 4 — 공시 변화 및 이익의 질(Quality of Earnings) 분석

1. 연도별 Risk Factors 요약을 비교해 식별하세요:
   신규 추가된 리스크 / 삭제된 공시 / 표현 강도가 바뀐 항목 / 세그먼트 보고 방식 변경
   → 각 변화가 "왜 지금" 나타났는지 해석을 덧붙일 것
2. 이익의 질 평가: 발생액 수준, SBC 의존도, 일회성 조정 빈도, non-GAAP 조정의 공격성,
   현금전환율(FCF/순이익), 운전자본 움직임

[출력 필드]
- key_takeaway / data_gaps (공통)
- filing_deltas: list — {change_type: "신규 리스크"|"삭제"|"표현 변경"|"보고 변경",
  description, year, significance: 해석}
- earnings_quality: list — {heading: 평가 항목, paragraphs: list[str]}
- quality_flags: list[str] — 주의 신호 (없으면 빈 배열)

[데이터]
## 팩트팩
{factpack}
## 연도별 Risk Factors(Item 1A) 요약
{risk_summaries}
## 이익의 질 지표 (코드 계산: 발생액, 현금전환율, 운전자본 추이)
{qoe_metrics}
```

### P-05 — 경쟁 구도 및 고객 집중도 (Wave 1)

```
# 과업: 섹션 5 — 경쟁 구도 및 고객 집중도 분석

1. 주요 세그먼트별 경쟁 포지션: 주요 경쟁사, 상대적 시장 지위, 경쟁 우위/열위
   (전환비용, 가격결정력, 브랜드/네트워크/데이터/AI 우위 관점)
2. 피어 비교표를 해석: 성장률·마진·밸류에이션·자본 집약도에서 동사의 상대적 위치
3. 매출·공급망 집중 리스크: 공시된 고객 집중도, 하이퍼스케일러/플랫폼/유통사/정부 의존,
   중국·규제·지정학 노출

※ 이 섹션은 제공 데이터가 제한적일 수 있습니다. 데이터에 없는 경쟁사 정보를 일반 지식으로
  채우지 말고, 확인 불가 항목을 data_gaps에 적극적으로 기록하세요.

[출력 필드]
- key_takeaway / data_gaps (공통)
- segment_competition: list — {segment, competitors: list[str], position, advantages: list[str],
  disadvantages: list[str]}
- peer_comparison_analysis: list[str] — 피어 비교표 해석 문단들
- concentration_risks: list — {risk, evidence: 근거}

[데이터]
## 팩트팩
{factpack}
## 피어 비교표 (코드 계산: 성장률·마진·밸류에이션·자본 집약도)
{peer_table}
## 10-K 경쟁·고객 집중 관련 서술 발췌
{competition_excerpts}
```

### P-06 — 자본 배분 (Wave 1)

```
# 과업: 섹션 6 — 자본 배분 분석 (최근 5년)

현금흐름 시계열을 근거로 경영진의 자본 배분 퀄리티를 평가하세요.

1. 자사주 매입 vs SBC로 인한 주식 희석의 순효과 — 발행주식수 추이로 검증
2. M&A 트랙레코드 (규모와 이후 성과가 데이터로 확인되는 범위에서)
3. 부채 발행/상환 패턴과 재무 여력
4. 배당 정책의 일관성과 지속가능성
5. 재투자 수익률(ROIC 추세)과 자본 배분 우선순위의 정합성 —
   "이 경영진에게 $1를 맡기면 무엇을 하는가, 그것이 옳았는가"

[출력 필드]
- key_takeaway / data_gaps (공통)
- allocation_analysis: list — {heading: 평가 항목, paragraphs: list[str]}
- allocation_grade: {grade: "우수"|"양호"|"보통"|"미흡", rationale: str}

[데이터]
## 팩트팩
{factpack}
## 자본 배분 시계열 (코드 계산: 자사주/배당/부채/M&A 현금흐름, 발행주식수)
{capital_allocation_table}
```

### P-07 — 실적 발표 및 가이던스 (Wave 1)

```
# 과업: 섹션 7 — 실적 발표 및 가이던스 분석 (최근 8분기)

분기별 실적 보도자료 요약을 근거로 분석하세요.

1. 가이던스 변화 궤적: 분기별 상향/하향/유지, 코멘터리의 일관성, 수요 전망의 톤 변화
2. 가이던스 신뢰도: 과거 가이던스 대비 실제 실적 (비교 데이터가 있는 범위에서)
3. 경영진이 반복적으로 강조하는 주제와, 언급을 피하는 것으로 보이는 영역

※ 어닝스콜 트랜스크립트가 제공되지 않은 경우 보도자료 기반 분석의 한계를 data_gaps에 명시하세요.

[출력 필드]
- key_takeaway / data_gaps (공통)
- guidance_trajectory: list — {quarter: "FY25 Q3" 형식, action: "상향"|"하향"|"유지"|"미제시",
  summary: 해당 분기 핵심 메시지}
- credibility_assessment: str — 가이던스 신뢰도 평가
- recurring_themes: list[str] — 반복 강조 주제
- avoided_topics: list — {topic, evidence: 회피로 판단한 근거} (없으면 빈 배열)

[데이터]
## 팩트팩
{factpack}
## 분기별 실적 보도자료(8-K) 요약 (최근 8분기)
{earnings_releases}
## 가이던스 vs 실적 비교 (코드 계산, 가능한 범위)
{guidance_vs_actual}
```

### P-08 — 컨센서스 및 밸류에이션 (Wave 1)

```
# 과업: 섹션 8 — 애널리스트 컨센서스 및 밸류에이션 분석

1. 향후 2개 회계연도 컨센서스(매출, EPS)와 추정치 리비전 방향, 애널리스트 간 분산도 해석
   (분산이 크다 = 시장의 확신이 낮다는 신호로 활용)
2. 밸류에이션 지표(forward P/E, EV/EBITDA, EV/Sales, FCF Yield, PEG)를
   자체 역사적 밴드 및 피어와 비교 — "지금 비싼가, 싼가, 왜 그런 멀티플을 받는가"
3. 확률적 시나리오 분석: Bull / Base / Bear 각각의 핵심 전제와 밸류에이션 함의
4. 현재 주가에 내재된 가정 판정 — "What must go right?"

[출력 필드]
- key_takeaway / data_gaps (공통)
- consensus_analysis: list[str] — 컨센서스·리비전 해석 문단들
- valuation_analysis: list — {heading: 지표/관점, paragraphs: list[str]}
- scenarios: list (정확히 3개) — {case: "Bull"|"Base"|"Bear", probability_pct: int,
  assumptions: list[str], implication: str}
- embedded_expectations: str — 현 주가 내재 가정

[데이터]
## 팩트팩
{factpack}
## 컨센서스·밸류에이션 표 (yfinance, 코드 계산: 추정치, 멀티플, 역사적 밴드)
{consensus_table}
```

### P-09 — 기술적 분석 및 핵심 리스크 (Wave 1)

```
# 과업: 섹션 9 — 기술적 분석(간략) 및 핵심 리스크

1. 기술적 지표표를 근거로 간략히 서술 (전체 3문단 이내, 펀더멘털 대비 부차적 비중 유지):
   장기 추세, 주요 지지/저항 수준, S&P500 대비 상대강도, 이동평균 배열, 거래량 특징
2. 리스크를 두 층위로 명확히 구분:
   - 단기 실행 리스크: 분기 실적, 가이던스 달성, 제품 출시 등
   - 장기 구조적/실존적 리스크: 기술 대체, 규제, 경쟁 구조 변화, 비즈니스 모델 침식

[출력 필드]
- key_takeaway / data_gaps (공통)
- technical_summary: list[str] — 최대 3문단
- short_term_risks: list — {risk, rationale}
- structural_risks: list — {risk, rationale}

[데이터]
## 팩트팩
{factpack}
## 기술적 지표 (코드 계산: 이동평균, 52주 밴드, S&P500 상대강도, 거래량 추이)
{technical_table}
```

### P-01 — Executive Summary (Wave 2)

```
# 과업: 섹션 1 — Executive Summary

아래는 이미 작성된 섹션 2~10의 핵심 결론입니다. 이를 종합해 리포트 최상단에 놓일
Executive Summary를 작성하세요. **새로운 사실이나 수치를 추가하지 말고**,
아래 결론들과 팩트팩 범위 안에서만 종합하세요.

1. 회사가 무엇을 하는 기업이고 핵심 비즈니스 모델이 무엇인가 (2~3문장)
2. 투자 논거(investment case)를 정보 밀도 높은 불렛 5~10개로
3. 핵심 강세 요인 vs 핵심 약세/리스크 요인
4. 비즈니스 퀄리티 종합 평가와, 현재 주가를 움직이는 "핵심 논쟁(Key Debate)" 한 가지

[출력 필드]
- business_overview: str
- investment_case: list[str] — 불렛 5~10개
- bull_points: list[str] / bear_points: list[str]
- quality_assessment: str
- key_debate: str
- data_gaps (공통)

[데이터]
## 팩트팩
{factpack}
## 섹션별 핵심 결론 (key_takeaway 모음)
{wave1_takeaways}
```

### P-10 — Variant Perception 및 최종 평가 (Wave 2)

```
# 과업: 섹션 10 — Variant Perception 및 최종 평가

섹션 2~9의 결론을 종합해 작성하세요. 새로운 사실·수치를 추가하지 마세요.

1. Variant Perception: 시장 컨센서스가 놓치거나 오해하고 있는 지점은 무엇인가?
   차별화된 장기 투자자들이 논쟁하는 주제 중 일반 투자자가 놓치는 것은?
2. 5개 축 평점 (1~10, 각 평점마다 근거 1~2문장 필수):
   비즈니스 퀄리티 / 해자 내구성 / 경영진 퀄리티 / 재투자 퀄리티 / 재무 복원력
3. 분기마다 모니터링해야 할 핵심 KPI 정확히 3개
4. 투자 논거를 완전히 무효화(invalidate)할 구체적 시그널

[출력 필드]
- variant_perception: list[str] — 서술 문단들
- ratings: list (정확히 5개) — {axis: 평가 축, score: 1~10, rationale}
- monitoring_kpis: list (정확히 3개) — {kpi, why: 왜 이것을 봐야 하는가}
- thesis_killers: list[str]
- data_gaps (공통)

[데이터]
## 팩트팩
{factpack}
## 섹션별 핵심 결론 (key_takeaway 모음)
{wave1_takeaways}
```

### P-QA — 검수 패스 (선택, 조립 후)

```
다음은 자동 생성된 {company_name}({ticker}) 리서치 리포트 전문입니다.
아래 기준으로만 점검하고 문제 목록을 출력하세요. 리포트를 수정하거나 재작성하지 마세요.

1. 섹션 간 수치 모순: 같은 지표를 다른 값으로 언급한 곳
2. 섹션 간 결론 충돌: 예) 섹션 3은 마진 개선 지속을 전망하는데 섹션 10은 마진 압박을
   핵심 리스크로 제시하면서 상호 참조가 없는 경우
3. 용어 표기 불일치: 같은 개념을 다른 용어로 지칭
4. 스타일 위반: 경어체 사용, 금액/비율 표기 형식 이탈

[출력 필드]
- issues: list — {type: "수치 모순"|"결론 충돌"|"용어 불일치"|"스타일 위반",
  location: 섹션 번호, description}  (문제 없으면 빈 배열)

[리포트 전문]
{report_md}
```

### 팩트팩 형식 (참고 — 코드가 생성, 프롬프트 아님)

```
### 회사 개요
{ticker} | {company_name} | {exchange} | {sector} | 시가총액 ${mcap}B | 기준일 {as_of}

### 5년 재무 시계열 (FY 기준, $M)          ← XBRL companyfacts에서 코드 계산
| 지표 | FY21 | FY22 | FY23 | FY24 | FY25 |
| 매출 / YoY / GPM / OPM / NPM / FCF / FCF마진 / SBC / R&D / Capex / ROIC / 발행주식수 | ... |

### 밸류에이션·컨센서스 (기준일 현재)       ← yfinance에서 코드 계산
Forward P/E {x} | EV/EBITDA {x} | EV/Sales {x} | FCF Yield {%} | PEG {x}
FY+1 컨센서스: 매출 ${}B / EPS ${} | FY+2: 매출 ${}B / EPS ${}
※ 결측 항목은 "N/A(사유)"로 표기 — 섹션 생성 시 data_gaps 처리의 근거가 됨
```

---

## 6. Stage 1 — CLI 파이프라인 (서버·DB 없이)

> 목표: `python scripts/generate_report.py AAPL -o AAPL.md` 한 줄로 리포트가 나오는 상태.
> 신규 `research-backend/` 디렉토리에서 개발. 기존 backend/frontend는 일절 수정하지 않는다.

### 디렉토리 구조

```
research-backend/
  app/
    config.py                     # GEMINI_API_KEY 등 (독립 .env)
    model_config.yaml             # 섹션(flash)/사전요약(flash-lite) 모델 설정
    pipeline/
      edgar.py                    # CIK 매핑, Submissions, 원문 수집·Item 분리
      financials.py               # XBRL → 5년 시계열 계산, yfinance 지표
      factpack.py                 # 팩트팩 조립 (5장 형식)
      sections.py                 # 섹션 레지스트리 (아래)
      generate.py                 # 오케스트레이션 (Map → Wave 1 → Wave 2)
      assemble.py                 # 최종 Markdown 조립 (목차·수치 표·출처)
    prompts/                      # 5장의 P-SYS, P-MAP, P-01 ~ P-10, P-QA
  scripts/generate_report.py      # CLI 진입점
  requirements.txt
  .env.example
```

**섹션 레지스트리** — 섹션 추가/수정이 파일 1곳으로 끝나도록:

```python
@dataclass
class SectionSpec:
    number: int
    title_ko: str
    prompt_file: str                      # "P-03" 등
    output_schema: type[BaseModel]        # SectionBase 상속
    data_keys: list[str]                  # 팩트팩 외 주입 데이터 키
    wave: int                             # 1 or 2
    renderer: Callable[[BaseModel], str]  # 구조화 출력 → Markdown
```

### 개발 편의 장치

- **파일 캐시**: EDGAR 응답·원문·사전 요약을 로컬 캐시 (공시는 불변) → 프롬프트 튜닝 반복 시 수집 재사용
- **섹션 단독 실행**: `--section 3` 옵션 → 특정 섹션만 재생성해 튜닝 속도 확보
- **중간 산출물 덤프**: 팩트팩·섹션별 JSON을 함께 저장 → 품질 문제의 원인(데이터 vs 프롬프트) 분리 진단

### 작업 순서

1. `edgar.py` — CIK 매핑 → Submissions → 원문 수집 → Item 분리 (User-Agent, 10 req/s 준수)
2. `financials.py` + `factpack.py` — XBRL 계산 검증이 전체 품질의 토대이므로 먼저 완성
3. 5장 프롬프트를 파일로 배치, 섹션 스키마·렌더러 구현
4. `generate.py` + `assemble.py` — Map/Wave 오케스트레이션, 섹션 부분 실패 허용
5. **품질 검증**: AAPL, NVDA, 소형주, 20-F 외국 기업 등 5개 내외 티커로 생성 → 프롬프트/스키마 튜닝 반복
6. 섹션 범위: 데이터 확실한 **2, 3, 4, 6, 8, 9 + Wave 2(1, 10)** 먼저. 5·7은 대체 데이터로 시도 후 품질 미달 시 Stage 4로 이연

---

## 7. Stage 2 — 독립 API 서버화

추가 구현: `app/main.py`(독립 FastAPI), `app/routers/research_router.py`(2-3의 API),
`app/services/cache_service.py`, `migrations/002_research.sql`, `Dockerfile`.

### DB (기존 Supabase 프로젝트에 테이블만 추가)

```sql
CREATE TABLE IF NOT EXISTS research_reports (
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    progress        VARCHAR(100),            -- "섹션 생성 중 (5/10)" 등
    lang            VARCHAR(5)  NOT NULL DEFAULT 'ko',
    report_md       TEXT,
    sections        JSONB,                   -- 섹션별 구조화 출력 원본 (재조립/디버깅)
    sources         JSONB,                   -- filing accession/URL 목록
    model_version   VARCHAR(50),
    error_message   TEXT,
    requested_by    UUID,                    -- Stage 3에서 사용
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS filings (         -- Stage 1 파일 캐시의 DB 이관
    id              SERIAL PRIMARY KEY,
    ticker_id       INTEGER NOT NULL REFERENCES tickers(id) ON DELETE CASCADE,
    accession_no    VARCHAR(30) NOT NULL UNIQUE,
    form_type       VARCHAR(10) NOT NULL,
    period_end      DATE,
    section_texts   JSONB,
    section_summaries JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_research_ticker_date ON research_reports(ticker_id, created_at DESC);
CREATE INDEX idx_research_user_date   ON research_reports(requested_by, created_at DESC);
CREATE INDEX idx_filings_ticker       ON filings(ticker_id, form_type, period_end DESC);
```

### 비동기 잡 + 배포

- FastAPI `BackgroundTasks` 실행, `progress` 갱신. 고아 잡: `started_at` 15분 초과 시 `failed` 전환
- **별도 Cloud Run 서비스**로 배포 (기존 backend와 분리):
  리서치 잡은 CPU always allocated 필수 → 기존 API의 request 과금과 격리, 독립 스케일링, 장애 격리
- 캐시 TTL: 완료 리포트 7일(168h) 재사용
- 검증: Swagger(`/docs`)로 잡 생성 → 폴링 → 리포트 확인. 프론트 없이 팀 내부 시연 가능

---

## 8. Stage 3 — 본 서비스 연동

**백엔드**: `POST /v1/research/{symbol}`에 Supabase Auth 토큰 검증(익명 불가), 사용자당 일일 한도(예: 5회 — `requested_by` 카운트), CORS는 기존 Vercel 패턴 재사용.

**프론트엔드**:

| 작업 | 내용 |
|---|---|
| 환경변수 | `NEXT_PUBLIC_RESEARCH_API_URL` (별도 Cloud Run URL) |
| API 클라이언트 | `lib/api.ts`에 `api.research.create / get / getJob` + 타입 |
| Markdown 렌더러 | `react-markdown` + `remark-gfm` (표 필수) |
| 리서치 탭 | `app/stock/[symbol]/page.tsx`에 "Brief / Deep Research" 탭 |
| 리포트 뷰 | `components/research/ReportView.tsx` — 목차(섹션 고정이라 하드코딩 가능), 출처, 생성 시각 |
| 진행 UI | `components/research/ResearchProgress.tsx` — 5초 폴링, `progress` 표시 |
| 미로그인 | 생성 버튼 → `/auth` 유도 |
| 문서 | README API 표·기능 소개 갱신 |

---

## 9. Stage 4 — 고도화 (선택)

- 섹션 5·7 데이터 보강: 트랜스크립트 유료 API(2-2) 연동
- 섹션 순차 노출: 완성된 섹션부터 프론트 표시 (구조 고정이라 부분 렌더링 자연스러움)
- 리포트 히스토리·이전 분기 비교 / Markdown·PDF 내보내기
- 자동 갱신: 신규 10-Q/10-K 감지 시 재생성 스케줄러
- 잡 큐 이관: BackgroundTasks → Cloud Tasks

---

## 10. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| 섹션 간 톤·형식 불일치 | 구조화 출력 + 코드 렌더링 + P-SYS 공통 주입 (4장) |
| 섹션 간 수치 모순 | 팩트팩 단일 출처, 수치 표는 코드 생성, P-QA로 모니터링 |
| flash 분석 깊이 한계 | Stage 1 검증에서 판단, 부족한 섹션만 pro 승격 (model_config 섹션별 오버라이드) |
| XBRL 태그 편차 | 태그 fallback 목록 유지, 결측은 팩트팩에 "N/A(사유)" → data_gaps 규칙으로 처리 |
| EDGAR rate limit (10 req/s) | User-Agent 준수, 파일/DB 캐시 (공시 불변 → 영구 캐시) |
| yfinance 비공식 API 변동 | 결측 허용 설계, 영향을 섹션 8·9로 격리 |
| Cloud Run 백그라운드 잡 유실 | 별도 서비스 + CPU always allocated + 고아 잡 타임아웃 |
| 티커별 데이터 편차 (20-F, 신규 상장) | form_type fallback(10-K→20-F), 커버리지 한계 리포트 상단 명시 |
| 부분 실패 | 섹션 단위 격리 — 실패 섹션만 표기하고 리포트 완성 |
| LLM 비용 | flash 병렬 단가 억제 + 인증 필수 + 일일 한도 + 7일 캐시 |
