# Cloud Run 배포 — 남은 작업 가이드

> plan_stage3.md §1의 작업 3~7. PR #29 머지 후 이 문서 순서대로 진행한다.
> 전제: 작업 1(리서치 rate limit)·2(변경 커밋)는 완료되어 PR #29에 포함됨.

## 현재 배포 상태

| 항목 | 값 |
|---|---|
| 서비스명 | `fin-aily-us` (추정 — 아래 사전 확인에서 검증) |
| 리전 | `asia-northeast1` |
| URL | `https://fin-aily-us-96426296927.asia-northeast1.run.app` |
| 프론트 | Vercel `https://fin-aily-us.vercel.app`, `NEXT_PUBLIC_API_URL`로 백엔드 참조 |
| Dockerfile | `backend/Dockerfile` — `PORT` env 준수, 수정 불필요 |

기존 배포는 뉴스/티커 기능만 있던 시점의 것. 이번 재배포로 리서치 라우터 + 백그라운드 잡이 추가되므로 **CPU 설정 변경이 필수**다 (아래 참조).

---

## 작업 3+4. Cloud Run 재배포 + env 갱신

### 3-1. 사전 확인

```bash
# 인증·프로젝트 확인
gcloud auth list
gcloud config get-value project

# 서비스명·현재 설정 확인 (env, 시크릿, CPU 설정 포함)
gcloud run services list --region asia-northeast1
gcloud run services describe fin-aily-us --region asia-northeast1
```

확인할 것:
- [ ] 서비스명이 `fin-aily-us`가 맞는지
- [ ] `GEMINI_API_KEY`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`가 env 또는 Secret Manager로 이미 설정돼 있는지 → **있으면 deploy 시 자동 유지됨** (`--set-env-vars`는 명시한 키만 갱신). 없으면 3-2 커맨드에 추가
- [ ] 현재 CPU throttling / min-instances 값 (변경 전 기록용)

### 3-2. 배포 커맨드

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

**플래그 이유** (빼면 안 됨):

| 플래그 | 이유 |
|---|---|
| `--no-cpu-throttling` | POST 응답 반환 후에도 `BackgroundTasks` 잡이 2~4분 실행됨. 기본값(request-based)은 응답 후 CPU를 회수해 잡이 사실상 멈춤 |
| `--min-instances 1` | 유휴 시 인스턴스 회수로 실행 중인 잡이 중도 종료되는 것 방지. 죽은 잡은 15분 뒤 `cleanup_stale_jobs`가 failed 처리하지만 사용자 경험상 완주가 낫다 |
| `--memory 1Gi` | 파이프라인 + `reports/`·`.cache/` 로컬 쓰기(Cloud Run 파일시스템은 인메모리 = 메모리 소비) 여유분 |
| `--timeout` | 설정 불필요 — POST는 즉시 반환하고 잡은 요청 수명과 무관 |

**비용**: `--min-instances 1` + `--no-cpu-throttling` = instance-based billing 상시 과금 (asia-northeast1, 1 vCPU/1Gi 기준 대략 월 $50 내외 — free tier 적용 전). 부담이면 Stage 4에서 Cloud Tasks/Jobs 이관으로 절감. `--min-instances 0`으로 낮추는 절충안은 잡 중단 리스크를 감수하는 것.

**CORS 주의**: `CORS_ORIGINS`는 프로덕션 도메인만. Vercel preview 도메인(`fin-aily-*.vercel.app`)은 `main.py`의 `allow_origin_regex`가 커버.

### 3-3. 배포 직후 검증

`DEBUG=false`라 `/docs`(Swagger)는 프로덕션에서 닫혀 있음 → curl로 검증한다.

```bash
BASE=https://fin-aily-us-96426296927.asia-northeast1.run.app

# 헬스체크
curl -s $BASE/health                          # {"status":"ok"}

# 기존 기능 무회귀
curl -s "$BASE/v1/tickers/search?q=AAPL" | head -c 300

# 리서치: 생성 → 폴링 → 완료 (2~4분 소요)
curl -s -X POST $BASE/v1/research/AAPL        # job_id 확인, status: pending
curl -s $BASE/v1/research/jobs/<job_id>       # running → completed까지 반복
curl -s $BASE/v1/research/AAPL | head -c 500  # 완료 후 report_md 반환

# rate limit: POST 6회 연속 → 6번째 429
for i in 1 2 3 4 5 6; do curl -s -o /dev/null -w "%{http_code}\n" -X POST $BASE/v1/research/TEST$i; done
```

실패 시 로그: `gcloud run services logs read fin-aily-us --region asia-northeast1 --limit 50`

### 3-4. 롤백 (문제 발생 시)

```bash
gcloud run revisions list --service fin-aily-us --region asia-northeast1
gcloud run services update-traffic fin-aily-us --region asia-northeast1 \
  --to-revisions <직전-revision>=100
```

---

## 작업 5. Vercel 확인

- [ ] Vercel 프로젝트 env에서 `NEXT_PUBLIC_API_URL` 확인 — 값이 `https://fin-aily-us-96426296927.asia-northeast1.run.app/v1` (**`/v1` 포함**)인지
- [ ] PR #29 머지 → main push로 Vercel 자동 배포 확인 (react-markdown 계열 추가 후 빌드 통과 여부)
- [ ] `NEXT_PUBLIC_RESEARCH_API_URL`은 **불필요** (폐기된 계획의 잔재 — 설정돼 있으면 삭제)

## 작업 6. 프로덕션 스모크 테스트

plan_stage3.md §3과 동일. 체크리스트:

1. [ ] **첫 생성**: 리포트 없는 티커 → 리서치 탭 진입 시 자동 생성 → progress 변화 → 2~4분 후 자동 렌더
2. [ ] **캐시 히트**: 같은 티커 재진입 → 즉시 렌더
3. [ ] **강제 재생성**: "새로 생성" 버튼(force=true) → 새 잡 → 완료 후 갱신
4. [ ] **실패 복구**: 존재하지 않는 티커(`ZZZZZZ`) → failed → 에러 + "다시 시도"
5. [ ] **동시 요청**: 두 탭에서 같은 티커 → 같은 job_id 폴링 (중복 잡 없음)
6. [ ] **렌더 품질**: 표 가로 스크롤, 목차 앵커 점프, 모바일 뷰
7. [ ] **라우트**: 리서치 URL 직접 접속·새로고침 복원, 뒤로가기, 기존 `/stock/[symbol]` 무회귀
8. [ ] **rate limit**: 3-3의 curl 6연속 → 429
9. [ ] **잡 생존** (Cloud Run 핵심 검증): 생성 직후 브라우저 닫기 → 5분 뒤 재진입 → 완료 리포트 표시. 실패하면 `--no-cpu-throttling`/`--min-instances` 설정이 실제 적용됐는지 `gcloud run services describe`로 재확인

## 작업 7. README 갱신

- [ ] 리서치 API 3개 엔드포인트 표 추가 (`POST /v1/research/{symbol}`(+`?force=true`), `GET /v1/research/{symbol}`, `GET /v1/research/jobs/{job_id}`) + rate limit 명시
- [ ] Deep Lab 기능 소개 (홈 탭, `/stock/[symbol]/research`)
- [ ] 프론트 env 표 확인 (`NEXT_PUBLIC_API_URL` 하나면 충분함을 명시)
- [ ] 배포 섹션에 Cloud Run 플래그(`--no-cpu-throttling`, `--min-instances 1`) 및 이유 한 줄

---

## Stage 4 이연 항목 (이번 범위 아님)

- Cloud Tasks/Jobs로 잡 이관 → `--min-instances 0` 복귀로 상시 과금 제거
- 인증·일일 한도 재도입 (멀티유저 공개 시 — 코드는 `dependencies.py`/`research_cache_service.py`에 보존됨)
- 섹션 순차 노출, 리포트 히스토리, PDF 내보내기, 신규 공시 감지 자동 재생성
