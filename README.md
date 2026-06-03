# fin-aily-us

AI 기술로 미국 주식 뉴스를 투자자 관점의 핵심 인사이트로 정제해주는 웹 서비스.

**🌐 서비스 URL**

| | URL |
|---|---|
| Frontend | https://fin-aily-us.vercel.app |
| Backend API | https://fin-aily-us-xn7f7tn7la-an.a.run.app/docs |

---

## 주요 기능

### Ticker Brief (티커 브리핑)
- 티커(예: AAPL, TSLA) 검색 시 Yahoo Finance 최신 뉴스 즉시 수집
- Google Gemini가 투자자 관점의 핵심 불렛 포인트로 요약
- 뉴스 흐름의 긍정·부정 여부를 수치화한 **Sentiment Score** 제공
- 결과는 DB에 캐시되어 재검색 시 빠르게 응답

### Market Pulse (마켓 펄스)
- Yahoo Finance RSS 기반으로 시장 전체 흐름 AI 요약
- 별도 검색 없이 접속 즉시 현재 가장 뜨거운 경제 이슈 확인

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| Backend | FastAPI, Python 3.13 |
| 뉴스 수집 | yfinance, feedparser (RSS) |
| AI 분석 | Google Gemini |
| Database | Supabase (PostgreSQL) |
| Frontend | Next.js (App Router), TypeScript |
| 스타일 | Tailwind CSS |
| Auth | Supabase Auth |
| 배포 | Backend: Google Cloud Run · Frontend: Vercel |

---

## 로컬 실행

### 사전 요구사항

- Python 3.11+
- Node.js 18+
- [Gemini API 키](https://aistudio.google.com/app/apikey)
- [Supabase 프로젝트](https://supabase.com)

### 1. Supabase 설정

1. Supabase 대시보드에서 새 프로젝트 생성
2. **Project Settings > API** 에서 `URL`, `anon key`, `service_role key` 복사
3. **SQL Editor** 에서 마이그레이션 파일 실행:

```
backend/migrations/001_initial_schema.sql
```

### 2. Backend

```bash
cd backend
cp .env.example .env
# .env 파일에서 API 키 및 Supabase 정보 입력

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs` (`.env`에 `DEBUG=true` 필요)

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
# .env.local 파일에서 Supabase 정보 입력

npm install
npm run dev
```

브라우저에서 `http://localhost:3000` 접속

---

## 환경변수

### Backend (`backend/.env`)

```
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

---

## API

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/v1/news/{symbol}` | 종목 최신 뉴스 수집 + AI 요약 |
| `GET` | `/v1/news/market-pulse` | 시장 전체 뉴스 AI 요약 |
| `GET` | `/v1/tickers/search?q={쿼리}` | 티커·종목명 자동완성 검색 (Rate Limit: 30회/분) |

---

## 개발 예정

### Deep Research (심층 리서치)
SEC EDGAR 10-K/10-Q 공시 및 어닝스콜 트랜스크립트를 기반으로 애널리스트 수준의 종합 리포트를 생성하는 기능. Map-Reduce LLM 파이프라인으로 대용량 문서를 섹션별로 병렬 요약한 뒤 하나의 리포트로 합성.

---

## 관련 프로젝트

- [fin-aily-kr](https://github.com/jonas-jun/fin-aily-kr) — 한국 상장 종목 AI 애널리스트 리포트 분석 (네이버 증권 + Gemini)
