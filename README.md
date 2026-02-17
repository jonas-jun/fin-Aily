# 📈 StockInsight

> AI 기반 글로벌 주식 뉴스 종합 요약 플랫폼

티커를 검색하면 최신 뉴스 10개를 AI가 한 번에 읽고, bullet point 종합 요약과 Sentiment Score를 제공합니다.

---

## 목차

1. [프로젝트 구조](#프로젝트-구조)
2. [사전 준비](#사전-준비)
3. [빠른 시작](#빠른-시작)
4. [백엔드 설정](#백엔드-설정)
5. [프론트엔드 설정](#프론트엔드-설정)
6. [Supabase 설정](#supabase-설정)
7. [주요 기능 및 API](#주요-기능-및-api)
8. [배포](#배포)
9. [트러블슈팅](#트러블슈팅)

---

## 프로젝트 구조

```
project/
├── backend/                        # Python FastAPI 백엔드
│   ├── app/
│   │   ├── main.py                 # FastAPI 앱 진입점
│   │   ├── config.py               # 환경 변수 설정
│   │   ├── dependencies.py         # DB / 인증 의존성
│   │   ├── middleware/
│   │   │   └── rate_limit_middleware.py
│   │   ├── routers/
│   │   │   ├── news_router.py      # GET /news/{symbol}
│   │   │   ├── tickers_router.py   # GET /tickers/search
│   │   │   ├── watchlist_router.py # GET/POST/DELETE /watchlist
│   │   │   ├── sentiment_router.py # GET /sentiment/overview
│   │   │   └── users_router.py     # GET/PATCH /users/me
│   │   └── services/
│   │       ├── news_service.py         # yfinance / RSS 뉴스 수집
│   │       ├── summarization_service.py # Claude / Gemini API 종합 요약 (1회 호출)
│   │       └── cache_service.py        # ticker 단위 TTL 캐시
│   ├── migrations/
│   │   └── 001_initial_schema.sql  # 전체 DB 스키마
│   ├── pyproject.toml
│   └── .env.example
│
└── frontend/                       # Next.js 14 프론트엔드
    ├── app/
    │   ├── page.tsx                # 홈 (검색 + 인기 종목)
    │   ├── stock/[symbol]/page.tsx # 종목 뉴스 페이지
    │   ├── watchlist/page.tsx      # 워치리스트
    │   └── auth/page.tsx           # 로그인 / 회원가입
    ├── components/
    │   ├── news/
    │   │   ├── DigestCard.tsx      # AI 종합 요약 + Sentiment
    │   │   └── ArticleList.tsx     # 기사 제목/링크 목록
    │   └── ui/
    │       ├── TickerSearch.tsx    # 자동완성 검색창
    │       ├── Header.tsx
    │       └── Skeletons.tsx
    ├── lib/
    │   ├── api.ts                  # 백엔드 API 클라이언트
    │   ├── supabase.ts             # Supabase 브라우저 클라이언트
    │   └── utils.ts                # 공통 유틸 함수
    ├── package.json
    └── .env.local.example
```

---

## 사전 준비

아래 계정 및 도구가 필요합니다.

| 항목 | 용도 | 링크 |
|------|------|------|
| **Node.js 18+** | 프론트엔드 실행 | https://nodejs.org |
| **Python 3.11+** | 백엔드 실행 | https://python.org |
| **Poetry** | Python 패키지 관리 | https://python-poetry.org |
| **Anthropic API Key** | Claude AI 요약 (Claude 사용 시) | https://console.anthropic.com |
| **Gemini API Key** | Gemini AI 요약 (Gemini 사용 시) | https://aistudio.google.com |
| **Supabase 프로젝트** | DB + 인증 | https://supabase.com |

---

## 빠른 시작

### 1. 압축 해제

```bash
tar -xzf stock-insight.tar.gz
cd project
```

### 2. 백엔드 실행

```bash
cd backend
cp .env.example .env        # 환경 변수 입력 (아래 참조)
poetry install
poetry run uvicorn app.main:app --reload --port 8000
```

### 3. 프론트엔드 실행

```bash
cd frontend
cp .env.local.example .env.local   # 환경 변수 입력 (아래 참조)
npm install
npm run dev
```

브라우저에서 http://localhost:3000 접속

---

## 백엔드 설정

### 환경 변수 (`backend/.env`)

`.env.example`을 복사 후 값을 채웁니다.

```env
# Summarization Provider: "claude" | "gemini"  ← 사용할 AI 모델 선택
SUMMARIZATION_PROVIDER=claude

# Anthropic (Claude 사용 시 필수)
ANTHROPIC_API_KEY=sk-ant-...         # https://console.anthropic.com

# Gemini (Gemini 사용 시 필수)
GEMINI_API_KEY=AIza...               # https://aistudio.google.com

# Supabase
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_ANON_KEY=eyJ...             # Supabase > Project Settings > API
SUPABASE_SERVICE_ROLE_KEY=eyJ...     # Supabase > Project Settings > API

# App
APP_ENV=development
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]
```

> **모델 전환 방법**: `SUMMARIZATION_PROVIDER` 값만 바꾸면 됩니다. 서버 재시작이 필요합니다.
>
> | `SUMMARIZATION_PROVIDER` | 필요한 키 | 사용 모델 |
> |--------------------------|-----------|-----------|
> | `claude` (기본값) | `ANTHROPIC_API_KEY` | claude-haiku-4-5-20251001 |
> | `gemini` | `GEMINI_API_KEY` | gemini-2.0-flash |

### 패키지 설치 및 서버 실행

```bash
cd backend

# 의존성 설치
poetry install

# 개발 서버 (자동 리로드)
poetry run uvicorn app.main:app --reload --port 8000

# 프로덕션 서버
poetry run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

서버 실행 후 http://localhost:8000/docs 에서 API 문서를 확인할 수 있습니다. (`DEBUG=true` 필요)

---

## 프론트엔드 설정

### 환경 변수 (`frontend/.env.local`)

`.env.local.example`을 복사 후 값을 채웁니다.

```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
NEXT_PUBLIC_API_URL=http://localhost:8000/v1   # 백엔드 주소
```

### 패키지 설치 및 실행

```bash
cd frontend

npm install

# 개발 서버
npm run dev

# 프로덕션 빌드
npm run build
npm run start
```

---

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
| `watchlists` | 사용자 관심 종목 |
| `news_articles` | 수집된 뉴스 원문 |
| `ticker_summaries` | AI 종합 요약 캐시 (TTL 24h) |
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

---

## 주요 기능 및 API

### 뉴스 종합 요약 흐름

```
사용자가 "AAPL" 검색
    │
    ▼
[1] ticker_summaries 캐시 확인 (24h TTL)
    │
  캐시 HIT ──────────────────────────────┐
    │ MISS                               │
    ▼                                    │
[2] yfinance / RSS에서 뉴스 10개 수집     │
    │                                    │
    ▼                                    │
[3] AI API 1회 호출 (Claude 또는 Gemini) │
    - 10개 기사를 한 번에 전달            │
    - bullet 종합 요약 생성 (최대 10줄)   │
    - Sentiment Score 산출               │
    │                                    │
    ▼                                    │
[4] ticker_summaries에 캐시 저장          │
    │                                    │
    └─────────────────────────────────────┘
    ▼
[5] digest(종합 요약) + articles(기사 목록) 반환
```

### 주요 API 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| `GET` | `/v1/tickers/search?q=AAPL` | 티커 자동완성 | 불필요 |
| `GET` | `/v1/news/{symbol}` | 뉴스 + AI 종합 요약 | 선택 (비로그인 일 5회) |
| `GET` | `/v1/watchlist` | 관심 종목 조회 | 필요 |
| `POST` | `/v1/watchlist` | 관심 종목 추가 | 필요 |
| `DELETE` | `/v1/watchlist/{symbol}` | 관심 종목 제거 | 필요 |
| `GET` | `/v1/sentiment/overview` | Sentiment 대시보드 | 필요 |
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
      "애플이 1분기 매출 1,240억 달러를 기록하며 역대 최고 실적을 달성했다.",
      "iPhone 판매가 전년 대비 12% 증가하며 실적을 견인했다.",
      "서비스 부문 매출이 사상 최고치를 경신했다.",
      "팀 쿡 CEO는 인도 시장 확대 전략을 재확인했다.",
      "AI 기능 탑재 확대로 ASP 상승이 예상된다."
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

---

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

`summarization_service.py`의 `_build_prompt` 함수에서 "반드시 JSON만 출력" 지시가 있으나, 간혹 모델이 마크다운 펜스를 붙이는 경우가 있습니다. 이는 코드에서 자동으로 제거됩니다. 계속 문제가 되면 다른 provider로 전환해보세요 (`SUMMARIZATION_PROVIDER=gemini`), 또는 `summarization_service.py`의 `CLAUDE_MODEL`을 `claude-sonnet-4-5-20250929`로 올려보세요.

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
