# Sumup — 인증 제거 + 백엔드 통합 계획

> 목표: **개인 사용 모드**로 전환. 로그인 없이 모든 기능 사용 가능하게 하고,
> `deep_research/`(포트 8001)를 `backend/`(포트 8000)에 흡수해 **backend 하나 + frontend 하나**만 실행하면 되는 구조로 만든다.
> 인증은 나중에 다시 붙일 수 있도록 코드를 보존한 채 연결만 해제한다.

## 0. 현재 상태 (Stage 3 완료 시점)

| 영역 | 상태 |
|---|---|
| 실행 구조 | 3개 프로세스: `backend`(뉴스, 8000) + `deep_research`(리서치, 8001) + `frontend`(3000) |
| 인증 | 리서치 3개 엔드포인트 전부 Supabase JWT 필수 (`get_current_user`), 일일 한도 5회 (`requested_by` 기준) |
| 프론트 | `researchFetch`가 별도 `NEXT_PUBLIC_RESEARCH_API_URL` 사용, `DeepResearchView`에 로그인 유도·토큰 첨부·401/429 분기 존재 |
| 패키지 충돌 | 두 앱 모두 최상위 패키지가 `app` — `app.config`, `app.dependencies`, `app.services.cache_service` 이름 충돌 → 단순 mount 불가, 파일 이동 필요 |
| 의존성 | deep_research requirements ⊂ backend requirements (9개 전부 동일 버전) → **requirements.txt 변경 불필요** |
| DB | 같은 Supabase 프로젝트 공유, `requested_by`는 nullable → 스키마 변경 불필요 |

## 1. 결정 사항

1. **인증: 제거가 아니라 "연결 해제"** — `get_current_user` 함수는 남기고, 라우터의 `Depends(...)`와 프론트의 토큰 로직만 걷어낸다. 다시 붙일 때 diff가 최소가 되도록.
2. **일일 한도: 비활성화** — 한도는 사용자 식별(`requested_by`)에 의존하므로 인증 없이는 무의미. `count_jobs_today` 함수는 보존하되 호출하지 않음. `requested_by`는 `None`으로 기록.
3. **통합 방향: deep_research → backend 안으로 이동** — 리서치 코드를 `backend/app/` 하위로 옮기고 이름 충돌은 리네임으로 해결. CLI(`scripts/generate_report.py`)도 `backend/scripts/`로 이동, 이동 완료 후 `deep_research/` 디렉터리 삭제 (git 히스토리로 복구 가능).

## 2. 백엔드 통합 (`backend/`)

### 2-1. 파일 이동 매핑

| From (`deep_research/`) | To (`backend/`) | 비고 |
|---|---|---|
| `app/routers/research_router.py` | `app/routers/research_router.py` | 인증 해제 (아래 2-3) |
| `app/services/cache_service.py` | `app/services/research_cache_service.py` | **리네임** — 기존 뉴스 `cache_service.py`와 충돌 회피 |
| `app/pipeline/*` (9개 모듈) | `app/research_pipeline/*` | import 경로 일괄 치환 |
| `app/prompts/*.txt` (15개) | `app/research_pipeline/prompts/` | 파이프라인 옆으로 |
| `app/model_config.yaml` | `app/research_pipeline/model_config.yaml` | 경로 상수 수정 |
| `app/config.py`의 리서치 설정 | `app/config.py`(backend)에 **병합** | 아래 2-2 |
| `app/dependencies.py`의 `get_db`, `get_current_user` | `app/dependencies.py`(backend)에 병합 | 기존 backend 의존성과 중복 확인 후 정리 |
| `scripts/generate_report.py` | `backend/scripts/generate_report.py` | CLI 경로 수정 |
| `migrations/002_research.sql` | `backend/migrations/002_research.sql` | 이미 적용된 상태, 파일만 이동 |
| `README.md`의 리서치 내용 | 루트 `README.md`로 흡수 | 문서 단일화 |

이동 후 `deep_research/` 삭제.

### 2-2. 설정 병합 — `backend/app/config.py`

backend는 pydantic-settings, deep_research는 수동 dataclass 방식. **backend 방식으로 통일**하고 다음 키를 추가:

```
EDGAR_USER_AGENT, DEEP_RESEARCH_CACHE_DIR, DEEP_RESEARCH_OUTPUT_DIR,
RESEARCH_REPORT_TTL_HOURS(168), RESEARCH_JOB_TIMEOUT_MINUTES(15),
RESEARCH_API_USE_LLM(true), RESEARCH_API_RUN_QA(false)
```

- `RESEARCH_DAILY_LIMIT`은 제거 (한도 비활성화). 인증 재도입 시 함께 복구.
- 캐시/출력 디렉터리 기본값은 `backend/` 기준 상대경로로 재해석되는지 확인 (`.cache/`, `reports/`).
- `model_config.yaml` 로더(`load_model_config`)와 `_fallback_yaml`은 파이프라인 유틸로 이동.
- `backend/.env` + `.env.example`에 위 키 추가. `deep_research/.env`는 삭제.

### 2-3. 인증 연결 해제 — `research_router.py`

- 3개 엔드포인트에서 `user: dict = Depends(get_current_user)` 파라미터 제거.
- POST: `count_jobs_today` 검사 블록과 429 분기 제거, `create_job(..., requested_by=None)` (기본값이라 인자 자체 생략).
- `get_current_user`는 `dependencies.py`에 그대로 보존 + "현재 미사용, 인증 재도입 시 라우터에 재연결" 주석.
- 라우터 등록: `backend/app/main.py`에 `app.include_router(research_router.router, prefix="/v1")` 추가.

### 2-4. 미들웨어 확인 — `rate_limit_middleware.py`

- 기존 IP rate limit(30회/분)이 전역인지 경로별인지 확인.
- 리서치 폴링은 5초 간격(12회/분)이므로 전역 한도라면 `/v1/research/jobs/*`를 예외 처리하거나 한도 상향. **구현 시 실측으로 판단.**

### 2-5. 백그라운드 잡 주의점

- `run_research_job`은 FastAPI `BackgroundTasks`로 동작 — 같은 프로세스에 뉴스 API가 함께 살게 되므로, 리포트 생성 중에도 뉴스 응답이 막히지 않는지 확인 (파이프라인이 async이므로 문제 없을 것으로 예상, E2E에서 검증).
- Cloud Run 배포 시 이제 **통합 backend에** CPU always allocated 필요 (기존엔 리서치 서비스만 해당).

## 3. 프론트엔드 (`frontend/`)

### 3-1. API 클라이언트 — `lib/api.ts`

- `RESEARCH_BASE_URL`, `researchFetch` 제거 → `api.research.*`가 기존 `apiFetch`(단일 `NEXT_PUBLIC_API_URL`) 사용.
- `api.research.{create,get,getJob}`에서 `token` 파라미터 제거.
- `fetchFrom` 분리가 무의미해지면 원래의 단일 `apiFetch`로 되돌림 (에러 규약 동일 유지).

### 3-2. 리서치 뷰 — `components/research/DeepResearchView.tsx`

- `getToken`/`getSession` 로직, `signed_out` phase, 로그인 유도 UI, 401→`/auth` 리다이렉트, 429 한도 안내 분기 **제거**.
- 상태 머신 단순화: `loading → has_report | no_report → generating → has_report | error`.
- 폴링 구조(setTimeout 재귀, 15분 상한, 언마운트 취소)는 그대로 유지.
- Supabase 클라이언트 import 제거 (이 컴포넌트에서 더 이상 불필요).

### 3-3. 환경변수

- `frontend/.env.local` + `.env.local.example`에서 `NEXT_PUBLIC_RESEARCH_API_URL` 제거.
- `/auth` 페이지와 Supabase 로그인 자체는 **삭제하지 않음** (watchlist 등 기존 용도 + 재도입 대비). 리서치 플로우에서 참조만 끊는다.

## 4. 작업 순서

| # | 작업 | 검증 |
|---|---|---|
| 1 | 파일 이동 + import 경로 치환 (`app.pipeline` → `app.research_pipeline`, `cache_service` → `research_cache_service`) | `python -c "import app.main"` 통과 |
| 2 | config/dependencies 병합, `.env` 키 이전 | 백엔드 부팅 + `/health` |
| 3 | 라우터 인증 해제 + main.py 등록 | 토큰 없이 `POST /v1/research/AAPL` → 200 |
| 4 | rate limit 경로 확인·조정 | 폴링 12회/분이 429 안 맞는지 |
| 5 | CLI 스크립트 경로 수정 | `python scripts/generate_report.py AAPL --no-llm` 동작 |
| 6 | 프론트 api.ts + DeepResearchView 단순화, env 정리 | `tsc --noEmit` + `next build` |
| 7 | `deep_research/` 삭제, README/plan 문서 갱신 | 루트 README의 실행 절차가 2-프로세스로 갱신됨 |
| 8 | E2E: backend(8000) + frontend(3000)만 실행 | 아래 시나리오 |

## 5. E2E 검증 시나리오

1. **2-프로세스 실행**: `uvicorn app.main:app --port 8000` (conda finaily) + `npm run dev` 만으로 전체 기능 동작.
2. **브리핑 탭**: 뉴스 요약 정상 (기존 회귀 없음).
3. **리서치 탭 (비로그인)**: 로그인 없이 진입 → 리포트 조회/생성/폴링/렌더 전부 동작.
4. **생성 중 뉴스 사용**: 리포트 생성 진행 중에 브리핑 탭·티커 검색이 정상 응답하는지 (단일 프로세스 블로킹 확인).
5. **캐시 히트**: 같은 티커 재생성 → `cached: true` 즉시 반환.
6. **실패 복구**: 잘못된 티커 → failed → 다시 시도.
7. **CLI**: `backend/scripts/generate_report.py` 단독 실행.

## 6. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| import 치환 누락으로 런타임 ImportError | 이동 직후 전 모듈 import 스모크 (`app.main` + 파이프라인 전체) |
| 뉴스/리서치 서비스 함수 이름 혼동 | 리서치 쪽은 `research_` 접두사로 일관 리네임 |
| config 방식 차이(pydantic-settings vs dataclass)로 파이프라인이 `AppConfig` 필드 참조 실패 | 파이프라인이 쓰는 필드 목록을 먼저 grep으로 추출해 인터페이스 유지 또는 어댑터 제공 |
| rate limit이 리서치 폴링을 차단 | 작업 4에서 실측 후 예외 경로 추가 |
| 인증 재도입 시 복구 비용 | 제거가 아닌 미연결: `get_current_user`·`count_jobs_today` 보존, 이 문서에 재연결 지점 명시 (라우터 Depends 3곳 + 프론트 token 파라미터 + 한도 검사 블록) |
| CPU always allocated 미설정 시 배포 후 잡 중단 | 배포 체크리스트에 명시 (통합 backend 기준) |

## 7. 범위 제외

- 인증·일일 한도 재도입 (다음 단계, 이 문서 6번의 재연결 지점 참고)
- `/auth` 페이지·Supabase 로그인 삭제 (유지)
- Cloud Run 실제 배포 (로컬 확인까지만)
