# Deep Research Stage 3 — 본 서비스 연동 (현행화: 2026-07-06)

> 원래 계획(독립 `deep_research/` API 서버 + Supabase 인증 + 일일 한도)에서 **구현 중 방향이 전환**되어,
> 이 문서는 as-built 상태와 남은 배포 작업을 기준으로 재작성되었다.
> 이전 계획 대비 핵심 변경: ① 리서치 API를 `backend/`에 통합 ② 인증·일일 한도 제거(개인 사용 모드) ③ 리포트 없으면 자동 생성 UX.

## 0. As-built 현재 상태

### 아키텍처

| 영역 | 상태 |
|---|---|
| 리서치 API | `backend/app/routers/research_router.py` — 기존 backend에 통합. `POST /v1/research/{symbol}`(+`?force=true`), `GET /v1/research/{symbol}`, `GET /v1/research/jobs/{job_id}` |
| 잡 실행 | FastAPI `BackgroundTasks` — POST 응답 후 서버 프로세스 내에서 2~4분 실행. 15분 초과 잡은 `cleanup_stale_jobs`가 failed 처리 |
| 캐시 | `research_reports` 테이블, TTL 168h(7일). TTL 지난 리포트는 GET에서 404 → 프론트가 자동 재생성 |
| 인증 | **없음 (개인 사용 모드)** — `get_current_user`(dependencies.py)와 `count_jobs_today`/`requested_by`(research_cache_service.py)는 코드에 보존, 라우터 미연결. 재도입 시 라우터에 Depends + 한도 검사만 복구하면 됨 |
| 프론트 API | 단일 `NEXT_PUBLIC_API_URL` — backend 통합으로 별도 `NEXT_PUBLIC_RESEARCH_API_URL`/`researchFetch` 불필요(폐기) |
| 배포(기존) | Backend: Cloud Run `https://fin-aily-us-96426296927.asia-northeast1.run.app` (asia-northeast1) · Frontend: Vercel `https://fin-aily-us.vercel.app` |

### 프론트 (구현 완료)

- **라우트 기반 탭**: `app/stock/[symbol]/layout.tsx`(탭바만 소유) + `page.tsx`(브리핑, 무수정) + `research/page.tsx`. `components/stock/StockTabNav.tsx`.
- **컴포넌트**: `components/research/DeepResearchView.tsx`(상태 머신), `ResearchProgress.tsx`, `ReportView.tsx`(react-markdown + remark-gfm + rehype-raw — 설치 완료).
- **UX 상태 머신** (미로그인 화면·생성 버튼 없음):

```
loading ─(GET latest)─▶ has_report            : ReportView + "새로 생성"(force=true)
                    └─▶ 404(7일 이내 없음)     : 자동 POST create → polling
polling ─(5초 setTimeout 재귀, 최대 15분)─▶ completed → GET latest → has_report
                                        └─▶ failed    → 에러 + "다시 시도"
```

- **홈 Deep Lab 탭**: `app/page.tsx`에 `?tab=research` 추가, `DeepLabLanding.tsx` + `TickerSearch(destination="research")` → `/stock/{symbol}/research` 직행.
- 리포트 제목 리브랜딩: "Deep Research" → "Deep Lab Report" (`assemble.py`).

### 이전 계획에서 폐기된 항목

- Supabase JWT 인증(전 엔드포인트), 일일 생성 한도(`RESEARCH_DAILY_LIMIT`), 미로그인 유도 화면 → 개인 사용 모드로 제거. E2E 시나리오의 "미로그인"·"한도 초과"도 함께 폐기.
- 독립 `deep_research/` 서비스와 그에 따른 별도 Cloud Run 서비스/ENV.

## 1. 남은 작업 프로세스 (순차 진행)

| # | 작업 | 파일/대상 | 검증 |
|---|---|---|---|
| 1 | **리서치 rate limit 추가** — 익명 + 자동 생성 조합의 비용 방어선. `RATE_LIMITS`에 `"/v1/research": (10, 60)` 추가 (인메모리 IP 기준, 단일 인스턴스 전제) | `backend/app/middleware/rate_limit_middleware.py` | 로컬에서 11회 연속 호출 → 429 |
| 2 | **미커밋 변경 정리·커밋** — Deep Lab 탭, force 재생성, 404 자동 생성, TTL 기반 GET, untracked `DeepLabLanding.tsx` 포함. `backend/example*.md`, `frontend/tsconfig.tsbuildinfo`는 커밋 제외(.gitignore 검토) | `git` | `npm run build`(frontend) 통과 후 커밋 |
| 3 | **Cloud Run 재배포** — 기존 서비스에 리서치 통합 버전 배포 + 백그라운드 잡 생존 설정 | `backend/` (아래 커맨드) | `/health` 200, Swagger로 POST→폴링→완료 1회 |
| 4 | **Cloud Run env 갱신** — 리서치 관련 env 추가 | Cloud Run 서비스 설정 | 배포 후 로그에 설정 로드 확인 |
| 5 | **Vercel 확인** — `NEXT_PUBLIC_API_URL`이 Cloud Run URL(`/v1` 포함)인지 확인, 프론트 재배포 | Vercel env | 프로덕션에서 리서치 탭 동작 |
| 6 | **프로덕션 스모크 테스트** — 아래 §3 시나리오 | — | — |
| 7 | **README 갱신** — 리서치 API 3개 엔드포인트 표, Deep Lab 기능 소개, env 표 | `README.md` | — |

1↔2는 독립적이라 순서 교체 가능. 3·4는 한 번의 `gcloud run deploy`로 함께 처리한다.

## 2. Cloud Run 배포 상세 (작업 3·4)

`backend/Dockerfile`은 Cloud Run 표준(`PORT` env) 준수 — 그대로 사용.

**핵심 플래그** — POST 응답 후에도 백그라운드 잡이 2~4분 돌아야 하므로:

- `--no-cpu-throttling` : 응답 반환 후에도 CPU 할당 유지 (없으면 잡이 사실상 멈춤)
- `--min-instances=1` : 유휴 시 인스턴스 회수로 잡이 중도 종료되는 것 방지
- `--memory=1Gi` : 파이프라인 + 로컬 파일 쓰기(`reports/`, `.cache/`는 인메모리 fs) 여유분
- `--timeout` 은 무관 (POST는 즉시 반환, 잡은 요청 수명과 무관하게 실행)

```bash
cd backend
gcloud run deploy fin-aily-us \
  --source . \
  --region asia-northeast1 \
  --no-cpu-throttling \
  --min-instances 1 \
  --memory 1Gi \
  --allow-unauthenticated \
  --set-env-vars "APP_ENV=production,DEBUG=false" \
  --set-env-vars "EDGAR_USER_AGENT=fin-aily-us deep-research junhot08@gmail.com" \
  --set-env-vars "RESEARCH_REPORT_TTL_HOURS=168,RESEARCH_JOB_TIMEOUT_MINUTES=15" \
  --set-env-vars "RESEARCH_API_USE_LLM=true,RESEARCH_API_RUN_QA=false" \
  --set-env-vars 'CORS_ORIGINS=["http://localhost:3000","https://fin-aily-us.vercel.app"]'
```

- 시크릿(`GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`)은 기존 서비스 설정에 이미 있으면 유지됨(`--set-env-vars`는 지정한 키만 갱신). 없으면 Secret Manager 연결 또는 `--set-env-vars` 추가.
- Vercel preview 도메인은 main.py의 `allow_origin_regex`가 커버하므로 CORS_ORIGINS에는 프로덕션 도메인만.
- **비용 주의**: `--min-instances=1` + `--no-cpu-throttling`은 상시 과금(instance-based billing). 개인 사용 수준에서 수용 여부 확인. 절감하려면 잡 실행을 Cloud Tasks/Jobs로 이관(Stage 4)해야 하며, 그 전까지는 이 설정이 안전한 최소치.

## 3. 프로덕션 스모크 테스트 (작업 6)

1. **첫 생성**: 리포트 없는 티커 → 리서치 탭 진입 시 자동 생성 → progress 문자열 변화 → 2~4분 후 자동 렌더.
2. **캐시 히트**: 같은 티커 재진입 → 즉시 렌더(생성 없음).
3. **강제 재생성**: "새로 생성" 버튼 → `force=true`로 새 잡 → 완료 후 갱신.
4. **실패 복구**: 존재하지 않는 티커(`ZZZZZZ`) → failed → 에러 + "다시 시도".
5. **동시 요청**: 두 탭에서 같은 티커 → 같은 job_id 폴링(중복 잡 없음).
6. **렌더 품질**: 표 가로 스크롤, 목차 앵커 점프, 모바일 뷰.
7. **라우트**: 리서치 URL 직접 접속·새로고침 복원, 뒤로가기로 브리핑 복귀, 기존 `/stock/[symbol]` 무회귀.
8. **rate limit**: `/v1/research` 연속 호출 시 429 (curl로 확인).
9. **잡 생존**: 생성 직후 브라우저를 닫고 5분 뒤 재진입 → 완료 리포트 확인 (Cloud Run 백그라운드 생존 검증).

## 4. 리스크 및 대응 (현행)

| 리스크 | 대응 |
|---|---|
| 익명 + 자동 생성 → 크롤러/남용으로 LLM 비용 발생 | 작업 1의 IP rate limit이 1차 방어. 공개 확대 시 인증·일일 한도 재도입(코드 보존됨 — 라우터 연결만 복구) |
| Cloud Run 인스턴스 회수로 백그라운드 잡 중단 | `--no-cpu-throttling` + `--min-instances=1`. 죽은 잡은 15분 후 `cleanup_stale_jobs`가 failed 처리 → 프론트 "다시 시도" |
| 인메모리 rate limit이 다중 인스턴스에서 분산됨 | 개인 사용 = 사실상 단일 인스턴스라 수용. 스케일아웃 시 Redis 교체 |
| TTL 만료 리포트 자동 재생성으로 방문마다 비용 | 의도된 동작(항상 신선한 리포트). 부담되면 TTL 연장 또는 생성 버튼 방식 복귀 |
| 폴링 중 이탈 | 잡은 서버에서 계속 진행 → 재진입 시 GET latest 또는 active job 재연결 |
| `rehype-raw` XSS | 자사 파이프라인 산출물만 렌더. `<script>` 원천 제거 여부 1회 점검(스모크 6과 병행) |

## 5. 범위 제외 (Stage 4로 이연)

- 인증·일일 한도 재도입(멀티유저 공개 시), Cloud Tasks/Jobs 잡 큐 이관(min-instances 비용 절감)
- 섹션 순차 노출(부분 렌더링), 리포트 히스토리·분기 비교, PDF 내보내기
- 신규 공시 감지 자동 재생성, 어닝스콜 트랜스크립트 등 외부 데이터 연동
