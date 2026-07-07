# fin-aily-us

AI 기술로 미국 주식 뉴스를 투자자 관점의 핵심 인사이트로 정제해주는 웹 서비스.

**🌐 서비스 URL**

| | URL |
|---|---|
| Frontend | https://fin-aily-us.vercel.app |
| Backend API | https://fin-aily-us-437915204376.asia-northeast1.run.app |

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

### Deep Lab (심층 리서치)
- 홈의 **Deep Lab** 탭에서 티커 검색 → 리서치 페이지(`/stock/{symbol}/research`)로 진입, SEC EDGAR 10-K/10-Q 공시 기반 애널리스트 수준 리포트 생성
- Map-Reduce LLM 파이프라인으로 대용량 공시를 섹션별 병렬 요약 후 단일 리포트로 합성 (목차·표·출처 포함)
- 생성은 백그라운드 잡으로 진행되며 프론트가 5초 간격 폴링으로 진행 상태 표시 (약 2~4분)
- 완료 리포트는 168시간 캐시. 현재 **개인 사용 모드**라 로그인 없이 누구나 조회·생성 가능 (인증·사용자별 한도는 추후 재도입 예정, 재도입 절차는 GitHub 이슈 #8에 문서화)

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
2. **Project Settings > API** 에서 `URL`, `service_role key` 복사
3. **SQL Editor** 에서 마이그레이션 파일을 순서대로 실행:

```
backend/migrations/001_initial_schema.sql
backend/migrations/002_research.sql
```

### 2. Backend

뉴스 API와 심층 리서치 API가 **하나의 FastAPI 앱**으로 통합되어 있다. 프로세스 하나만 띄우면 전체 기능이 동작한다.

```bash
cd backend
cp .env.example .env
# .env 파일에서 API 키 및 Supabase 정보 입력 (심층 리서치용 EDGAR_USER_AGENT 등 포함)

pip install -r requirements.txt
# migrations/001_initial_schema.sql, migrations/002_research.sql 를 Supabase 프로젝트에 순서대로 실행
uvicorn app.main:app --reload --port 8000
```

Swagger UI: `http://localhost:8000/docs` (`.env`에 `DEBUG=true` 필요)

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local
# .env.local 파일에서 API URL 입력

npm install
npm run dev
```

브라우저에서 `http://localhost:3000` 접속 — backend(8000) + frontend(3000) 두 프로세스만으로 브리핑·심층 리서치 전체 기능을 사용할 수 있다.

---

## 환경변수

### Backend (`backend/.env`)

```
GEMINI_API_KEY=your-gemini-api-key

SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...

APP_ENV=development
DEBUG=true
CORS_ORIGINS=["http://localhost:3000"]

# Deep Research (심층 리서치)
EDGAR_USER_AGENT=fin-aily-us deep-research your-email@example.com
DEEP_RESEARCH_CACHE_DIR=.cache
DEEP_RESEARCH_OUTPUT_DIR=reports
RESEARCH_REPORT_TTL_HOURS=168
RESEARCH_JOB_TIMEOUT_MINUTES=15
RESEARCH_API_USE_LLM=true
RESEARCH_API_RUN_QA=false
```

### Frontend (`frontend/.env.local`)

```
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
```

백엔드 연동은 `NEXT_PUBLIC_API_URL` 하나면 충분하다 (**`/v1` 경로 포함**). 브리핑·심층 리서치 모두 같은 백엔드를 사용하므로 별도의 리서치 API URL 변수는 필요 없다.

---

## API

모든 엔드포인트는 하나의 backend(`backend/`, 포트 8000)에서 제공된다.

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/v1/news/{symbol}` | 종목 최신 뉴스 수집 + AI 요약 |
| `GET` | `/v1/news/market-pulse` | 시장 전체 뉴스 AI 요약 |
| `GET` | `/v1/tickers/search?q={쿼리}` | 티커·종목명 자동완성 검색 (Rate Limit: 30회/분) |
| `POST` | `/v1/research/{symbol}` | 심층 리서치 잡 시작 (캐시·진행 중 잡은 즉시 반환, `?force=true`로 강제 재생성) (Rate Limit: 5회/분/IP) |
| `GET` | `/v1/research/{symbol}` | 최신 완료 리포트 조회 |
| `GET` | `/v1/research/jobs/{job_id}` | 잡 상태·완료 리포트 폴링 |

> 현재 개인 사용 모드로 `/v1/research/*`는 인증 없이 열려 있다. 인증 로직(`get_current_user`)은 `backend/app/dependencies.py`에 보존되어 있어 필요 시 각 라우터에 `Depends`로 다시 연결할 수 있다.

---

## 배포

- **Frontend**: Vercel — main 브랜치 push 시 자동 배포. `NEXT_PUBLIC_API_URL`에 Cloud Run URL + `/v1` 설정 (값 변경 시 Redeploy 필요)
- **Backend**: Google Cloud Run — `--no-cpu-throttling`(응답 반환 후에도 백그라운드 리서치 잡이 CPU를 계속 사용해야 함)과 `--min-instances 1`(유휴 시 인스턴스 회수로 실행 중인 잡이 중단되는 것 방지) 플래그가 필수다. 상세 절차는 `working/cloudrun.md` 참조

---

## 관련 프로젝트

- [fin-aily-kr](https://github.com/jonas-jun/fin-aily-kr) — 한국 상장 종목 AI 애널리스트 리포트 분석 (네이버 증권 + Gemini)
