# fin-aily-us

AI 기술로 복잡한 미국 주식 뉴스를 투자자 관점의 핵심 인사이트로 정제해주는 웹 서비스.

티커를 검색하면 Yahoo Finance 최신 뉴스를 자동 수집하고, Google Gemini / Anthropic Claude가 핵심 포인트·감성 분석·시장 흐름을 한 페이지로 요약해드립니다.

**🌐 서비스 URL**

| | URL |
|---|---|
| Frontend | https://fin-aily-us.vercel.app |
| Backend API | https://fin-aily-us-xn7f7tn7la-an.a.run.app/docs |

---

## 주요 기능

### Ticker Brief (티커 브리핑)
- 티커(예: AAPL, TSLA) 검색 시 해당 종목의 최신 뉴스 즉시 수집
- AI가 투자자 관점의 핵심 불렛 포인트로 요약
- 뉴스 흐름의 긍정·부정 여부를 수치화한 **Sentiment Score** 제공

### Market Pulse (마켓 펄스)
- Yahoo Finance 최신 금융 뉴스 기반으로 시장 전체 흐름 요약
- 별도 검색 없이 접속 즉시 현재 가장 뜨거운 경제 이슈 확인

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI, Python 3.13 |
| 뉴스 수집 | yfinance, feedparser (RSS), newspaper3k |
| AI 분석 | Google Gemini / Anthropic Claude (YAML 기반 기능별 설정) |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js 16 (App Router), TypeScript |
| 스타일 | Tailwind CSS |
| Auth | Supabase Auth UI |
| 배포 | Backend: Google Cloud Run · Frontend: Vercel |

---

## 디자인

### 컬러 시스템

| 역할 | 색상 | 값 |
|---|---|---|
| Primary (강조·CTA) | Emerald Green | `#22C55E` |
| Brand (헤더·배경) | Navy Blue | `#1E3A5F` |

Tailwind 커스텀 컬러(`brand-green`, `brand-navy`)로 등록되어 있습니다.

### 로고

SVG 컴포넌트(`Logo.tsx`)로 구현되어 있습니다.

- Navy Blue `fin-aily` 워드마크 + Emerald Green 삼각형(▲) 아이콘
- 우측 상단 `US` 배지로 미국 서비스임을 명시
- `size` prop으로 `"header"` / `"hero"` 두 가지 크기 지원

---

## 디렉토리 구조

```
fin-aily-us/
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 앱 진입점
│   │   ├── config.py             # 환경변수 설정
│   │   ├── dependencies.py       # FastAPI 의존성 (DB 연결)
│   │   ├── model_config.yaml     # 기능별 AI 모델 및 캐시 TTL
│   │   ├── middleware/
│   │   │   └── rate_limit_middleware.py  # 슬라이딩 윈도우 Rate Limit
│   │   ├── routers/
│   │   │   ├── news_router.py         # 뉴스 수집 및 요약 엔드포인트
│   │   │   └── tickers_router.py      # 종목 검색 엔드포인트
│   │   └── services/
│   │       ├── news_service.py            # yfinance + RSS 뉴스 수집
│   │       ├── summarization_service.py   # Gemini / Claude AI 요약
│   │       ├── article_cache_service.py   # 기사 DB 캐시
│   │       └── cache_service.py           # 요약 결과 DB 캐시
│   ├── migrations/
│   │   └── 001_initial_schema.sql    # Supabase 테이블 스키마
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
└── frontend/
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx                  # 메인 홈 (Ticker Brief / Market Pulse 탭)
    │   ├── auth/page.tsx             # Supabase Auth UI
    │   └── stock/[symbol]/page.tsx   # 개별 종목 상세 페이지
    ├── components/
    │   ├── ui/
    │   │   ├── Header.tsx
    │   │   ├── Logo.tsx
    │   │   ├── TickerSearch.tsx
    │   │   └── Skeletons.tsx
    │   └── news/
    │       ├── DigestCard.tsx
    │       └── ArticleList.tsx
    ├── lib/
    │   ├── api.ts          # 백엔드 API 통신
    │   ├── supabase.ts     # 클라이언트 Supabase 설정
    │   └── utils.ts
    └── .env.local.example
```

---

## 로컬 실행

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- [Gemini API 키](https://aistudio.google.com/app/apikey) 또는 [Anthropic API 키](https://console.anthropic.com)
- [Supabase 프로젝트](https://supabase.com)

### 1. Supabase 설정

1. Supabase 대시보드에서 새 프로젝트 생성
2. **Project Settings > API** 에서 `URL`, `anon key`, `service_role key` 복사
3. **SQL Editor** 에서 아래 파일 실행하여 테이블 생성:

```
backend/migrations/001_initial_schema.sql
```

생성되는 테이블:

| 테이블 | 설명 |
|---|---|
| `tickers` | 종목 마스터 |
| `news_articles` | 수집된 뉴스 원문 캐시 |
| `ticker_summaries` | AI 요약 결과 캐시 |

### 2. Backend

```bash
cd backend

# 환경변수 설정
cp .env.example .env
# .env 파일에서 API 키 및 Supabase 정보 입력

# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행 (hot-reload)
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs` (`.env`에 `DEBUG=true` 필요)

### 3. Frontend

```bash
cd frontend

# 환경변수 설정
cp .env.local.example .env.local
# .env.local 파일에서 Supabase 정보 입력 (API URL은 기본값 그대로 사용 가능)

# 의존성 설치
npm install

# 개발 서버 실행
npm run dev
```

브라우저에서 `http://localhost:3000` 접속

---

## 환경변수

### Backend (`backend/.env`)

```
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=your-gemini-api-key

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...

APP_ENV=development
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]
```

### Frontend (`frontend/.env.local`)

```
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

### AI 모델 설정 (`backend/app/model_config.yaml`)

코드 수정 없이 기능별 AI 모델과 캐시 TTL을 변경할 수 있습니다.

```yaml
cache:
  article_ttl_hours: 0.5
  summary_ttl_hours: 0.5

features:
  market_pulse:
    provider: gemini   # "gemini" | "claude"
    model: gemini-3.1-flash-lite
    max_tokens: 1024

  ticker_brief:
    provider: gemini
    model: gemini-3.1-flash-lite
    max_tokens: 1024
```

---

## API

### 뉴스 및 요약

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/v1/news/{symbol}` | 특정 종목 최신 뉴스 수집 + AI 요약 |
| `GET` | `/v1/news/market-pulse` | 시장 전체 뉴스 AI 요약 |

**Query Parameters**

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `lang` | `ko` | 응답 언어 (`ko` / `en`) |
| `limit` | `10` | 수집할 뉴스 수 (1~20, `/news/{symbol}`만 해당) |

### 종목 검색

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/v1/tickers/search?q={쿼리}` | 티커·종목명 자동완성 검색 (Rate Limit: 30회/분) |

### 응답 예시

```json
// GET /v1/news/AAPL?lang=ko&limit=10
{
  "symbol": "AAPL",
  "company_name": "AAPL",
  "last_updated": "2026-05-16T09:30:00Z",
  "digest": {
    "summary": [
      {
        "point": "애플이 1분기 매출 1,240억 달러를 기록하며 역대 최고 실적을 달성했다.",
        "quote": "Apple posted record quarterly revenue of $124.3 billion, up 4 percent year over year."
      }
    ],
    "sentiment": { "score": 0.74, "label": "Positive" },
    "based_on_articles": 10
  },
  "articles": [
    {
      "id": 0,
      "title": "Apple Reports Record Q1 Revenue",
      "source": "Yahoo Finance",
      "url": "https://finance.yahoo.com/...",
      "published_at": "2026-05-16T08:00:00Z"
    }
  ]
}
```

---

## 트러블슈팅

**yfinance로 뉴스가 수집되지 않는다**

Yahoo Finance 의존성이 차단될 경우 `news_service.py`의 RSS 백업 소스가 자동으로 작동합니다.

**LLM 응답이 JSON 형식이 아닌 경우**

`summarization_service.py`에서 마크다운 펜스를 자동으로 제거합니다. 계속 문제가 되면 `model_config.yaml`에서 provider나 model을 변경해보세요.

**CORS 오류가 발생한다**

백엔드 `.env`의 `CORS_ORIGINS`에 프론트엔드 주소가 포함되어 있는지 확인하세요.

```
CORS_ORIGINS=["http://localhost:3000", "https://fin-aily-us.vercel.app"]
```

---

## 관련 프로젝트

- [fin-aily-kr](https://github.com/jonas-jun/fin-aily-kr) — 한국 상장 종목 AI 애널리스트 리포트 분석 (네이버 증권 + Gemini)
