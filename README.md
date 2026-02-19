# 📈 fin-aily (핀-에일리)

**fin-aily**는 AI 기술을 활용하여 복잡한 금융 뉴스를 투자자에게 꼭 필요한 핵심 정보로 정제해주는 스마트 주식 투자 비서 서비스입니다. "Finance + AI + Daily"의 의미를 담아 사용자가 매일의 시장 흐름을 가장 쉽고 빠르게 파악할 수 있도록 돕습니다.

---

## ✨ 주요 기능

### 1. Ticker Brief (티커 브리핑)
* **종목 맞춤형 분석**: 특정 티커(예: AAPL, TSLA)를 검색하면 해당 종목과 관련된 최신 뉴스 10개를 즉시 수집합니다.
* **10줄 핵심 요약**: 수집된 뉴스를 분석하여 투자자 관점에서 가장 중요한 10개의 불렛 포인트로 요약해 드립니다.
* **감성 분석 (Sentiment Analysis)**: 뉴스 흐름이 긍정적인지 부정적인지 AI가 판단하여 투자 지표로 활용할 수 있게 제공합니다.

### 2. Market Pulse (마켓 펄스)
* **시장 전체 흐름 파악**: MarketWatch의 실시간 Top Stories를 기반으로 현재 금융 시장의 맥박을 짚어줍니다.
* **똑똑한 비서 페르소나**: "주식투자에 도움을 주는 똑똑한 비서"라는 특화된 프롬프트를 사용하여 시장 전체의 인사이트를 요약합니다.
* **실시간 업데이트**: 별도의 검색 없이도 접속 즉시 현재 가장 뜨거운 경제 이슈들을 확인할 수 있습니다.

---

## 🛠 Tech Stack

### Frontend
* **Framework**: Next.js 14 (App Router)
* **Styling**: Tailwind CSS
* **Environment**: Node.js v20.20.0 (WSL2)

### Backend
* **Framework**: Python FastAPI
* **Data Sourcing**: yfinance, Feedparser (RSS)
* **AI Engine**: Google Gemini 2.5 Flash / Flash Lite, Anthropic Claude (YAML 기반 기능별 모델 설정)
* **Database**: Supabase (PostgreSQL)

---

## 🚀 시작하기

### 0. 사전 준비

아래 계정 및 도구가 필요합니다.

| 항목 | 용도 | 링크 |
|------|------|------|
| **Node.js 18+** | 프론트엔드 실행 | https://nodejs.org |
| **Python 3.11+** | 백엔드 실행 | https://python.org |
| **Poetry** | Python 패키지 관리 | https://python-poetry.org |
| **Anthropic API Key** | Claude AI 요약 (Claude 사용 시) | https://console.anthropic.com |
| **Gemini API Key** | Gemini AI 요약 (Gemini 사용 시) | https://aistudio.google.com |
| **Supabase 프로젝트** | DB + 인증 | https://supabase.com |

### 1. 환경 설정
본 프로젝트는 **WSL2** 환경 및 **Node.js v20.20.0**에 최적화되어 있습니다.

**Backend (`/backend/.env`)**
```env
ANTHROPIC_API_KEY=your_anthropic_api_key
GEMINI_API_KEY=your_gemini_api_key

SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_anon_key
```

**AI 모델 및 캐시 설정 (`/backend/app/model_config.yaml`)**

기능별 AI 모델과 캐시 TTL을 YAML 파일 하나로 관리합니다. 코드 수정 없이 모델 교체 및 캐시 주기 조정이 가능합니다.

```yaml
# 캐시 TTL 설정 (단위: 시간)
cache:
  article_ttl_hours: 0.5   # 기사 캐시
  summary_ttl_hours: 0.5   # 요약 캐시

# 기능별 AI 모델 설정
# provider: "gemini" | "claude"
features:
  market_pulse:
    provider: gemini
    model: gemini-2.5-flash-lite
    max_tokens: 1024

  ticker_brief:
    provider: gemini
    model: gemini-2.5-flash-lite
    max_tokens: 1024

# 신규 기능 추가 시 fallback 기본값
defaults:
  provider: gemini
  model: gemini-2.5-flash
  max_tokens: 1024
```

> **참고**: 기능별로 다른 provider를 사용할 수 있습니다. 예를 들어 Market Pulse는 `gemini`, Ticker Brief는 `claude`로 설정 가능합니다.

**Frontend (`/frontend/.env.local`)**
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000/v1   # 백엔드 주소
```

### 2. 실행 방법

**Backend (FastAPI)**

```bash
cd backend
poetry install
# 개발 서버 (자동 리로드)
poetry run uvicorn app.main:app --reload --port 8000
# 프로덕션 서버
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```
서버 실행 후 http://localhost:8000/docs 에서 API 문서를 확인할 수 있습니다. (`DEBUG=true` 필요)


**Frontend (Next.js)**

```bash
cd frontend
npm install
npm run dev
# 프로덕션 빌드
npm run build
npm run start
```
브라우저에서 http://localhost:3000 접속

---

## 📂 프로젝트 구조

`fin-aily`는 효율적인 유지보수를 위해 프론트엔드와 백엔드가 분리된 모노레포 구조를 가집니다.

```text
inv_secretary/
├── frontend/                # Next.js 14 기반 웹 대시보드
│   ├── app/
│   │   ├── page.tsx         # 메인 홈 (Brief/Pulse 탭 로직 및 fin-aily 브랜드 적용)
│   │   ├── layout.tsx       # 글로벌 레이아웃 및 폰트 설정
│   │   └── stock/[symbol]/  # 개별 종목 상세 페이지
│   ├── components/
│   │   ├── ui/              # TickerSearch, Header 등 공용 UI 컴포넌트
│   │   └── news/            # DigestCard, ArticleList 등 뉴스 관련 컴포넌트
│   └── lib/
│       ├── api.ts           # 백엔드 API 통신 규격 (Axios)
│       └── supabase.ts      # 클라이언트측 Supabase 설정
└── backend/                 # FastAPI 기반 뉴스 분석 서버
    ├── app/
    │   ├── main.py          # FastAPI 서버 진입점 및 미들웨어 설정
    │   ├── config.py        # 환경 변수 및 YAML 설정 로딩
    │   ├── model_config.yaml # 기능별 AI 모델 및 캐시 TTL 설정
    │   ├── routers/         # API 엔드포인트 정의 (news, tickers 등)
    │   └── services/        # 핵심 비즈니스 로직
    │       ├── news_service.py           # yfinance 및 RSS 뉴스 수집
    │       └── summarization_service.py  # Gemini/Claude 기반 AI 요약
    ├── migrations/          # Supabase(PostgreSQL) 테이블 스키마
    └── pyproject.toml       # Poetry 의존성 관리 설정
```

---

## 💡 API Reference

`fin-aily` 백엔드 서버에서 제공하는 주요 API 명세입니다. 모든 요청과 응답은 JSON 형식을 사용합니다.

### 1. 뉴스 및 요약 (News & Summarization)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/news/{symbol}` | `GET` | 특정 종목(티커)의 최신 뉴스 10개를 수집하고 AI가 10줄 이내의 핵심 포인트로 요약합니다. |
| `/news/market-pulse` | `GET` | MarketWatch의 Top Stories 10개를 가져와 "똑똑한 주식 투자 비서" 페르소나를 통해 시장 전체의 인사이트를 요약합니다. |

### 2. 종목 검색 (Ticker Search)

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/tickers/search` | `GET` | 사용자가 입력한 쿼리(예: "Apple" 또는 "AAPL")에 맞는 티커 심볼과 종목명을 검색하여 반환합니다. |



## Supabase 설정

### 1. 프로젝트 생성

1. https://supabase.com 에서 새 프로젝트 생성
2. **Project Settings > API** 에서 `URL`, `anon key`, `service_role key` 복사

### 2. DB 스키마 마이그레이션

Supabase 대시보드 **SQL Editor**에서 아래 파일의 내용을 실행합니다.

```
backend/migrations/001_initial_schema.sql
```

생성되는 테이블:

| 테이블 | 설명 |
|--------|------|
| `users` | 사용자 확장 프로필 |
| `tickers` | 종목 마스터 |
| `news_articles` | 수집된 뉴스 원문 |
| `ticker_summaries` | AI 종합 요약 캐시 (TTL은 `model_config.yaml`에서 설정) |
| `guest_rate_limits` | 비로그인 일일 조회 제한 |

### 3. 초기 종목 데이터 입력 (선택)

자동완성 검색을 위해 주요 종목을 미리 입력합니다.

```sql
INSERT INTO tickers (symbol, name, exchange, sector) VALUES
  ('AAPL',  'Apple Inc.',            'NASDAQ', 'Technology'),
  ('MSFT',  'Microsoft Corporation', 'NASDAQ', 'Technology'),
  ('NVDA',  'NVIDIA Corporation',    'NASDAQ', 'Technology'),
  ('TSLA',  'Tesla Inc.',            'NASDAQ', 'Consumer Cyclical'),
  ('AMZN',  'Amazon.com Inc.',       'NASDAQ', 'Consumer Cyclical'),
  ('GOOGL', 'Alphabet Inc.',         'NASDAQ', 'Technology'),
  ('META',  'Meta Platforms Inc.',   'NASDAQ', 'Technology');
```

### 4. Auth 설정

Supabase 대시보드 **Authentication > Providers** 에서 원하는 소셜 로그인을 활성화합니다.
- Email (기본 활성화)
- Google OAuth (선택)


### 주요 API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| `GET` | `/v1/tickers/search?q=AAPL` | 티커 자동완성 | 불필요 |
| `GET` | `/v1/news/{symbol}` | 뉴스 + AI 종합 요약 | 선택 (비로그인 일 5회) |
| `GET` | `/v1/users/me` | 내 프로필 | 필요 |
| `PATCH` | `/v1/users/me` | 프로필 수정 | 필요 |

### 뉴스 API 응답 예시

```json
// GET /v1/news/AAPL?lang=ko&limit=10
{
  "symbol": "AAPL",
  "company_name": "Apple Inc.",
  "last_updated": "2026-02-17T09:30:00Z",
  "digest": {
    "summary": [
      {
        "point": "애플이 1분기 매출 1,240억 달러를 기록하며 역대 최고 실적을 달성했다.",
        "quote": "Apple posted record quarterly revenue of $124.3 billion, up 4 percent year over year."
      },
      {
        "point": "iPhone 판매가 전년 대비 12% 증가하며 실적을 견인했다.",
        "quote": "iPhone revenue grew 12% year-over-year, driven by strong demand for the iPhone 16 lineup."
      },
      {
        "point": "서비스 부문 매출이 사상 최고치를 경신했다.",
        "quote": "Services revenue reached an all-time high of $26.3 billion, reflecting continued growth across the App Store, Apple Music, and iCloud."
      },
      {
        "point": "팀 쿡 CEO는 인도 시장 확대 전략을 재확인했다.",
        "quote": "CEO Tim Cook reaffirmed Apple's commitment to expanding its retail and manufacturing presence in India."
      },
      {
        "point": "AI 기능 탑재 확대로 ASP 상승이 예상된다.",
        "quote": "Analysts expect Apple Intelligence features to drive a higher average selling price in upcoming iPhone models."
      }
    ],
    "sentiment": { "score": 0.74, "label": "Positive" },
    "based_on_articles": 10
  },
  "articles": [
    {
      "id": 1234,
      "title": "Apple Reports Record Q1 Revenue",
      "source": "Yahoo Finance",
      "url": "https://finance.yahoo.com/...",
      "published_at": "2026-02-17T08:00:00Z"
    }
  ]
}
```


## 배포

### 백엔드 — Railway

1. [railway.app](https://railway.app) 에서 새 프로젝트 생성
2. GitHub 저장소 연결 후 `backend/` 디렉토리를 루트로 지정
3. **Variables** 탭에서 `.env` 환경 변수 입력
4. Start Command 설정:
   ```
   poetry run uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```

### 프론트엔드 — Vercel

1. [vercel.com](https://vercel.com) 에서 새 프로젝트 생성
2. GitHub 저장소 연결 후 **Root Directory** 를 `frontend/` 로 지정
3. **Environment Variables** 에서 아래 입력:
   ```
   NEXT_PUBLIC_SUPABASE_URL=...
   NEXT_PUBLIC_SUPABASE_ANON_KEY=...
   NEXT_PUBLIC_API_URL=https://your-backend.railway.app/v1
   ```
4. 배포 완료 후 백엔드의 `CORS_ORIGINS` 에 Vercel 도메인 추가

---

## 트러블슈팅

**Q. `yfinance`로 뉴스가 수집되지 않는다**

yfinance의 Yahoo Finance 의존성이 차단될 수 있습니다. `news_service.py`의 RSS 백업 소스가 자동으로 작동합니다. NewsAPI를 추가로 연동하려면 `.env`에 `NEWSAPI_KEY`를 추가하고 `news_service.py`에 핸들러를 구현하세요.

**Q. LLM 응답이 JSON 형식이 아닌 경우**

`summarization_service.py`의 `_build_prompt` 함수에서 "반드시 JSON만 출력" 지시가 있으나, 간혹 모델이 마크다운 펜스를 붙이는 경우가 있습니다. 이는 코드에서 자동으로 제거됩니다. 계속 문제가 되면 `model_config.yaml`에서 해당 기능의 provider나 model을 변경해보세요.

**Q. Supabase 무료 티어 용량 초과**

`ticker_summaries` 테이블의 오래된 캐시를 주기적으로 정리하는 쿼리를 Supabase **Scheduled Functions**에 등록하세요.

```sql
DELETE FROM ticker_summaries
WHERE created_at < NOW() - INTERVAL '7 days';
```

**Q. CORS 오류가 발생한다**

백엔드 `.env`의 `CORS_ORIGINS`에 프론트엔드 주소가 포함되어 있는지 확인하세요.

```env
CORS_ORIGINS=["http://localhost:3000", "https://your-app.vercel.app"]
```
