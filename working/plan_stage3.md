# Deep Research Stage 3 — 본 서비스 연동 계획

> Stage 2(독립 API 서버 + DB 캐시)까지 완료된 상태에서, 리서치 기능을 실제 서비스(프론트 + 인증 + 사용량 제한)에 연결한다.
> 원칙: **기존 backend/는 수정하지 않는다.** 변경은 `deep_research/`(리서치 API)와 `frontend/`에 한정된다.

## 0. 현재 상태 (Stage 2 완료 시점)

| 영역 | 상태 |
|---|---|
| 리서치 API | `deep_research/app/main.py` — FastAPI, `/v1/research/*` 3개 엔드포인트 + `/health` |
| CORS | Vercel 도메인 regex 허용 이미 구성됨 (`main.py`) |
| DB | `research_reports`(+`requested_by UUID` 컬럼, 인덱스 존재·미사용), `filings` 테이블, 캐시 TTL 168h |
| 인증 | **없음** — POST가 익명 허용 상태 (Stage 3에서 해결할 핵심 갭) |
| 프론트 | `lib/api.ts`의 `apiFetch`가 토큰 첨부 지원, Supabase 브라우저 클라이언트(`lib/supabase.ts`), `/auth` 로그인 페이지 존재 |
| 종목 페이지 | `app/stock/[symbol]/page.tsx` — 뉴스 단일 뷰, 탭 없음 |
| 마크다운 렌더러 | **없음** — `react-markdown` 계열 미설치 |

## 1. 목표와 완료 기준

로그인한 사용자가 종목 페이지의 "심층 리서치" 탭(`/stock/[symbol]/research`)에서:

1. 완료된 리포트가 있으면 즉시 렌더링된 리포트를 본다 (목차·표·출처 포함).
2. 없으면 "리포트 생성" 버튼 → 잡 시작 → 진행 상태를 폴링으로 보다가 완료 시 자동 렌더링.
3. 미로그인 사용자는 리서치 라우트 진입은 가능하되 생성/조회 시 `/auth`로 유도된다.
4. 사용자당 일일 생성 한도(기본 5회)가 적용되고, 초과 시 명확한 에러 메시지를 본다.

## 2. 백엔드 작업 (`deep_research/`)

### 2-1. Supabase JWT 인증 의존성 — `app/dependencies.py`

```python
from fastapi import Depends, Header, HTTPException

async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncClient = Depends(get_db),
) -> dict:
    """Authorization: Bearer <supabase_access_token> 검증. 익명 불가."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, detail={"code": "UNAUTHORIZED", "message": "로그인이 필요합니다."})
    token = authorization.split(" ", 1)[1].strip()
    try:
        result = await db.auth.get_user(token)   # Supabase에 토큰 검증 위임
        user = result.user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(401, detail={"code": "INVALID_TOKEN", "message": "유효하지 않은 세션입니다."})
    return {"id": user.id, "email": user.email}
```

- 검증 방식은 `auth.get_user(token)`(Supabase API 호출) 사용. 요청량이 적어 왕복 비용 무시 가능.
  트래픽이 늘면 `SUPABASE_JWT_SECRET`으로 로컬 HS256 검증으로 교체(후속 최적화, 지금은 하지 않음).
- 적용 범위: **3개 엔드포인트 전부** (POST 생성, GET 최신 리포트, GET 잡 폴링).
  리포트는 생성 비용이 든 자산이므로 조회도 로그인 필수로 한다. `/health`만 공개 유지.

### 2-2. 일일 사용량 제한 — `app/services/cache_service.py`

- `create_job(db, ticker_id, requested_by)`로 시그니처 확장, `research_reports.requested_by`에 기록 (기존 컬럼·인덱스 활용).
- 한도 검사 함수 추가:

```python
async def count_jobs_today(db, requested_by: str) -> int:
    # UTC 자정 기준. requested_by = user, 오늘 생성된 잡(status 무관) 카운트
    ...
```

- 라우터 POST 흐름 (기존 `create_research_job`에 삽입):

```
캐시 히트        → 한도 소모 없음, 그대로 반환 (cached: true)
진행 중 잡 존재  → 한도 소모 없음, 해당 잡 반환
신규 잡 생성 전  → count_jobs_today(user) >= RESEARCH_DAILY_LIMIT 이면
                   429 {"code": "DAILY_LIMIT_EXCEEDED", "message": "...", }
```

- `app/config.py`에 `RESEARCH_DAILY_LIMIT` (기본 5) 추가. `.env.example` 갱신.

### 2-3. 라우터 수정 — `app/routers/research_router.py`

- 3개 엔드포인트에 `user: dict = Depends(get_current_user)` 추가.
- POST: 한도 검사 + `create_job(..., requested_by=user["id"])`.
- 응답 스키마 변경 없음 (프론트 계약 안정 유지). 429/401 에러 바디는 기존 `ErrorBody{code, message}` 형식 재사용.

### 2-4. (선택) IP 기반 보조 rate limit

기존 `backend/app/middleware/rate_limit_middleware.py` 패턴을 복사해 `POST /v1/research/*`에 10회/분 정도의 IP 제한을 추가. 인증 우회 봇 대비 이중 방어.
우선순위 낮음 — 일일 한도가 주 방어선이므로 시간이 남으면 진행.

## 3. 프론트엔드 작업 (`frontend/`)

### 3-1. 의존성·환경변수

| 항목 | 내용 |
|---|---|
| 패키지 | `react-markdown`, `remark-gfm`(표 필수), `rehype-raw`(리포트 내 `<a id>` 앵커·`<br>` 렌더용) |
| 환경변수 | `NEXT_PUBLIC_RESEARCH_API_URL` — 리서치 API의 Cloud Run URL (`.env.local` + Vercel 설정) |

> 리포트 마크다운은 목차 앵커를 `<a id="...">` raw HTML로 포함하고 표 셀에 `<br>`을 쓰므로 `rehype-raw`가 없으면 목차 점프·셀 줄바꿈이 깨진다.

### 3-2. API 클라이언트 — `lib/api.ts`

- 리서치 API는 BASE_URL이 다르므로 `researchFetch` 래퍼를 추가 (기존 `apiFetch`와 동일 에러 규약, BASE만 `NEXT_PUBLIC_RESEARCH_API_URL`).
- 타입은 Stage 2 응답 스키마를 그대로 미러링:

```ts
export interface ResearchJob {
  job_id: number;
  symbol: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: string | null;
  cached: boolean;
  report: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface ResearchReport {
  symbol: string;
  status: string;
  report: string;
  sources: { form_type: string; accession_no: string; url: string; report_date?: string }[] | null;
  model_version: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export const api = {
  // ...기존...
  research: {
    create: (token: string, symbol: string): Promise<ResearchJob> =>
      researchFetch(`/research/${symbol}`, { method: "POST", token }),
    get: (token: string, symbol: string): Promise<ResearchReport> =>
      researchFetch(`/research/${symbol}`, { token }),
    getJob: (token: string, jobId: number): Promise<ResearchJob> =>
      researchFetch(`/research/jobs/${jobId}`, { token }),
  },
};
```

- 토큰 획득: `createClient().auth.getSession()` → `session.access_token`. 컴포넌트에서 매 호출 전에 가져온다 (Supabase가 자동 갱신).

### 3-3. 종목 페이지 탭 — **라우트 기반 분리**

상태(`useState`) 조건 렌더가 아니라, 실제 URL을 가진 별도 라우트로 탭을 나눈다. 리서치는 생성에 2~4분 걸리는 독립 플로우라 **딥링크·새로고침·뒤로가기·공유**가 URL로 동작하는 편이 UX·코드 분리 모두에서 낫다. 뉴스 로직은 파일 이동 없이 그대로 두어 "무수정" 원칙도 더 강하게 지킨다.

**최종 파일 구조** (`app/stock/[symbol]/`):

```
layout.tsx          신규 — 공통 종목 헤더 자리 + <StockTabNav> 렌더 + {children}
page.tsx            무수정 — 브리핑(뉴스). URL: /stock/[symbol]
research/page.tsx   신규 — 심층 리서치.   URL: /stock/[symbol]/research
```

- **URL 계약**: 기존 뉴스 URL `/stock/[symbol]`은 그대로 유지되어 기존 링크가 깨지지 않는다. 리서치는 `/stock/[symbol]/research`로 추가된다.
- **`layout.tsx`** (`"use client"`): `useParams`로 symbol을 받아 `<StockTabNav symbol={symbol} />`와 `{children}`만 렌더. 데이터 페칭은 각 `page.tsx`가 자체적으로 하므로 레이아웃은 얇게 유지(뉴스/리서치가 서로의 로딩·에러 상태에 얽히지 않음).
- **`components/stock/StockTabNav.tsx`** (신규): `usePathname()`으로 활성 탭 판별, `next/link`로 두 탭 링크(`브리핑` → `/stock/${symbol}`, `심층 리서치` → `/stock/${symbol}/research`). `prefetch`로 탭 전환 지연 최소화.
- **`page.tsx`(브리핑)는 코드 변경 없음** — 현재 페이지 헤더(symbol·company_name·last_updated)는 뉴스 응답에서 오므로 그대로 뉴스 페이지에 둔다. 레이아웃은 헤더를 소유하지 않고 탭바만 소유한다.
- **`research/page.tsx`**: `<DeepResearchView symbol={symbol} />`를 렌더하는 얇은 진입점. 리서치 자체 헤더(리포트 메타)는 3-4의 `ReportView`가 담당.
- 라우트 분리 덕에 탭 전환 시 각 페이지가 독립 마운트/언마운트되고 폴링·인터벌도 라우트 언마운트로 자연히 정리된다(상태 기반 숨김 처리 로직 불필요).

### 3-4. 신규 컴포넌트 — `components/research/`

**`DeepResearchView.tsx`** — 상태 머신 컨테이너:

```
idle ─(진입 시 GET latest)─▶ has_report        : ReportView 렌더 + "새로 생성" 버튼
                        └─▶ no_report(404)     : 소개 문구 + "리포트 생성" 버튼
generate 클릭 ─▶ POST create
   ├─ cached: true          → 즉시 has_report
   ├─ 401                   → /auth로 이동 (router.push)
   ├─ 429                   → "일일 생성 한도(5회)를 초과했습니다" 안내
   └─ job 반환              → polling 상태로 전환
polling ─(5초 간격 GET jobs/{id})─▶ completed → report 표시
   └─ failed → 에러 + "다시 시도" 버튼
```

- 미로그인 처리: 라우트 진입 시 `getSession()`이 null이면 조회 자체를 생략하고
  "심층 리서치는 로그인 후 이용할 수 있습니다" + 로그인 버튼(→ `/auth`)만 표시.
- 폴링은 `setInterval` 대신 `setTimeout` 재귀(응답 지연 시 중첩 방지), 언마운트 시 취소
  (다른 탭으로 이동 = 라우트 언마운트이므로 자동 정리됨).
  잡이 15분 타임아웃으로 `failed` 처리되는 서버 정책과 별개로, 클라이언트도 최대 15분에서 폴링 중단.

**`ResearchProgress.tsx`** — 진행 표시:

- 서버의 `progress` 문자열("리포트 생성 중" 등) + 경과 시간 표시, 스피너.
- 예상 소요 안내 문구 (약 2~4분).

**`ReportView.tsx`** — 리포트 렌더:

- `react-markdown` + `remark-gfm` + `rehype-raw`.
- prose 스타일: 표 가로 스크롤 래퍼(`overflow-x-auto`), 헤딩 간격 등 Tailwind로 최소한만.
- 헤더 메타: 생성 시각(`completed_at`, 기존 `timeAgo` 유틸 재사용), `model_version`.
- 목차는 리포트 마크다운에 이미 포함되어 있으므로 별도 구현하지 않는다 (앵커는 rehype-raw로 동작).
- 출처(`sources`)는 리포트 본문에도 있으므로 중복 렌더하지 않음 — 응답 필드는 후속(히스토리 등) 대비 타입만 유지.

### 3-5. 문서

- 루트 `README.md`: 리서치 API 표(3개 엔드포인트 + 인증 요구), 프론트 기능 소개, 환경변수 표에 `NEXT_PUBLIC_RESEARCH_API_URL` 추가.
- `deep_research/README.md`: 인증·한도 정책 추가.

## 4. 작업 순서

| # | 작업 | 파일 | 검증 방법 |
|---|---|---|---|
| 1 | 인증 의존성 + 라우터 적용 | `deep_research/app/dependencies.py`, `routers/research_router.py` | Swagger에서 토큰 없이 401, 유효 토큰으로 200 |
| 2 | 일일 한도 + requested_by 기록 | `services/cache_service.py`, `config.py`, `.env.example` | 같은 유저로 6회 POST → 6번째 429, DB에 requested_by 기록 확인 |
| 3 | 프론트 API 클라이언트 + 타입 | `lib/api.ts` | 브라우저 콘솔에서 호출 확인 |
| 4 | 마크다운 의존성 + ReportView | `package.json`, `components/research/ReportView.tsx` | 기존 완료 리포트로 표·목차 앵커 렌더 확인 |
| 5 | 라우트 탭 분리 + DeepResearchView + Progress | `app/stock/[symbol]/layout.tsx`, `research/page.tsx`, `components/stock/StockTabNav.tsx`, `components/research/*` | 아래 E2E 시나리오 |
| 6 | README 갱신 | `README.md`, `deep_research/README.md` | — |
| 7 | 배포 | Cloud Run env, Vercel env | 프로덕션 스모크 테스트 |

토큰 검증(1)과 프론트 클라이언트(3)는 독립적이라 병렬 진행 가능. 4는 3 없이도 로컬 md 파일로 개발 가능.

## 5. E2E 검증 시나리오

1. **미로그인**: 심층 리서치 탭(`/stock/[symbol]/research`) → 로그인 유도 화면 → 로그인 버튼 → `/auth` → 로그인 후 복귀.
2. **첫 생성**: 로그인 → 리포트 없는 티커 → 생성 버튼 → 진행 표시(progress 문자열 변화) → 2~4분 후 자동 렌더.
3. **캐시 히트**: 같은 티커에서 다시 생성 → 즉시 완료본 반환(`cached: true`), 한도 미소모 확인.
4. **한도 초과**: 서로 다른 티커로 한도+1회 생성 → 429 안내 문구.
5. **실패 복구**: 존재하지 않는 티커(예: `ZZZZZZ`) → 잡 failed → 에러 메시지 + 다시 시도 버튼.
6. **동시 요청**: 두 브라우저에서 같은 티커 동시 생성 → 둘 다 같은 job_id 폴링(중복 잡 없음).
7. **렌더 품질**: 표 넘침 없이 가로 스크롤, 목차 클릭 시 해당 섹션 이동, 모바일 뷰 확인.
8. **라우트 동작**: 리서치 URL 직접 접속·새로고침 시 상태 복원, 브라우저 뒤로가기로 브리핑 복귀, 기존 뉴스 링크(`/stock/[symbol]`) 무회귀 확인.

## 6. 배포 체크리스트

**리서치 API (Cloud Run, 기존 Stage 2 서비스에 env 추가)**
- [ ] `RESEARCH_DAILY_LIMIT=5`
- [ ] CORS: 프로덕션 Vercel 도메인이 `cors_origins`에 포함되는지 확인 (main.py의 regex는 preview용)
- [ ] CPU always allocated 유지 (백그라운드 잡)

**프론트 (Vercel)**
- [ ] `NEXT_PUBLIC_RESEARCH_API_URL=https://<research-api>.run.app/v1`
- [ ] 빌드 확인 (`react-markdown` 계열 추가 후)

## 7. 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| Supabase `auth.get_user` 왕복 지연 | 요청량 적어 수용. 병목 시 JWT 로컬 검증(HS256)으로 교체 — 코드 1곳(`get_current_user`)만 수정 |
| 폴링 중 세션 만료 | 매 폴링마다 `getSession()`으로 토큰 재획득 (Supabase 자동 리프레시 활용) |
| 긴 생성 시간 동안 이탈 | 잡은 서버에서 계속 진행 → 재진입 시 GET latest 또는 active job 재연결로 이어보기 |
| `rehype-raw`의 XSS 우려 | 리포트는 자사 파이프라인 생성물만 렌더(사용자 입력 아님). 그래도 `<script>` 계열은 마크다운 파이프라인에서 원천 제거되는지 1회 점검 |
| 429/401 에러 UX | ApiError.code 기반 분기 — 코드별 한국어 안내 문구를 DeepResearchView에서 매핑 |
| 탭 추가로 인한 기존 뉴스 회귀 | 라우트 분리로 `page.tsx`(뉴스)는 **파일·로직 무수정**. 신규는 `layout.tsx`/`research/`에만 추가되어 뉴스 코드에 손대지 않음 |
| 레이아웃 도입으로 뉴스 헤더 이중 렌더 | 헤더는 `page.tsx`에만 유지, `layout.tsx`는 탭바만 소유 — 헤더 소유권을 한 곳으로 고정 |

## 8. 범위 제외 (Stage 4로 이연)

- 섹션 순차 노출(부분 렌더링), 리포트 히스토리·분기 비교, PDF 내보내기
- 신규 공시 감지 자동 재생성, Cloud Tasks 잡 큐 이관
- 어닝스콜 트랜스크립트 등 외부 유료 데이터 연동
