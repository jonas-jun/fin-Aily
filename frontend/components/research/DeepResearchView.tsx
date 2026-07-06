"use client";

/**
 * components/research/DeepResearchView.tsx
 * ─────────────────────────────────────────
 * 심층 리서치 상태 머신 컨테이너.
 *
 *   loading   ─(GET latest)─▶ has_report  : ReportView + "새로 생성"
 *                          └▶ 404(7일 이내 리포트 없음) → 자동 POST create
 *   POST create ─▶ cached/completed → GET latest → has_report
 *               └▶ job(pending)     → polling
 *   polling ─(5초 setTimeout 재귀)─▶ completed → GET latest → has_report
 *                                 └▶ failed    → error + "다시 시도"
 *
 * 폴링은 setInterval 대신 setTimeout 재귀(중첩 방지), 언마운트 시 취소.
 * 개인 사용 모드 — 인증 없이 누구나 조회/생성 가능 (재도입 지점은 backend
 * app/dependencies.py의 get_current_user 주석 참고).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, type ResearchJob, type ResearchReport } from "@/lib/api";
import { ReportView } from "./ReportView";
import { ResearchProgress } from "./ResearchProgress";

type Phase = "loading" | "has_report" | "generating" | "error";

const POLL_INTERVAL_MS = 5_000;
const MAX_POLL_MS = 15 * 60 * 1_000; // 서버 잡 타임아웃과 별개로 클라이언트 상한

interface Props {
  symbol: string;
}

export function DeepResearchView({ symbol }: Props) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [report, setReport] = useState<ResearchReport | null>(null);
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pollStartedAt, setPollStartedAt] = useState(0);

  // 언마운트 시 폴링 취소용
  const cancelled = useRef(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearPoll = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  // ── 폴링 한 사이클 ──────────────────────────────────────────────────────────
  const poll = useCallback(
    async (jobId: number, startedAt: number) => {
      if (cancelled.current) return;

      if (Date.now() - startedAt > MAX_POLL_MS) {
        setErrorMsg("리포트 생성이 시간 내에 완료되지 않았습니다. 잠시 후 다시 시도해 주세요.");
        setPhase("error");
        return;
      }

      try {
        const updated = await api.research.getJob(jobId);
        if (cancelled.current) return;
        setJob(updated);

        if (updated.status === "completed") {
          const latest = await api.research.get(symbol);
          if (cancelled.current) return;
          setReport(latest);
          setPhase("has_report");
          return;
        }
        if (updated.status === "failed") {
          setErrorMsg(updated.error || "리포트 생성에 실패했습니다.");
          setPhase("error");
          return;
        }
        // pending | running → 다음 폴링 예약
        timeoutRef.current = setTimeout(() => poll(jobId, startedAt), POLL_INTERVAL_MS);
      } catch (err) {
        if (cancelled.current) return;
        setErrorMsg(err instanceof Error ? err.message : "진행 상태를 확인하지 못했습니다.");
        setPhase("error");
      }
    },
    [symbol],
  );

  // ── 생성 시작 ───────────────────────────────────────────────────────────────
  const handleGenerate = useCallback(async (force = false) => {
    setErrorMsg(null);
    setJob(null);
    const startedAt = Date.now();
    setPollStartedAt(startedAt);
    setPhase("generating");

    try {
      const created = await api.research.create(symbol, { force });
      if (cancelled.current) return;

      if (created.cached || (created.status === "completed" && created.report)) {
        const latest = await api.research.get(symbol);
        if (cancelled.current) return;
        setReport(latest);
        setPhase("has_report");
        return;
      }

      setJob(created);
      timeoutRef.current = setTimeout(() => poll(created.job_id, startedAt), POLL_INTERVAL_MS);
    } catch (err) {
      if (cancelled.current) return;
      setErrorMsg(err instanceof Error ? err.message : "리포트 생성을 시작하지 못했습니다.");
      setPhase("error");
    }
  }, [symbol, poll]);

  // ── 진입 시: 최신 리포트 조회 (7일 이내 리포트 없으면 자동 생성) ──────────────────
  useEffect(() => {
    cancelled.current = false;

    (async () => {
      try {
        const latest = await api.research.get(symbol);
        if (cancelled.current) return;
        setReport(latest);
        setPhase("has_report");
      } catch (err) {
        if (cancelled.current) return;
        if (err instanceof ApiError && err.status === 404) {
          handleGenerate();
        } else {
          setErrorMsg(err instanceof Error ? err.message : "리포트를 불러오지 못했습니다.");
          setPhase("error");
        }
      }
    })();

    return () => {
      cancelled.current = true;
      clearPoll();
    };
  }, [symbol, clearPoll, handleGenerate]);

  // ── 렌더 ────────────────────────────────────────────────────────────────────
  if (phase === "loading") {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-slate-400">
        불러오는 중…
      </div>
    );
  }

  if (phase === "generating") {
    return <ResearchProgress progress={job?.progress ?? null} startedAt={pollStartedAt} />;
  }

  if (phase === "error") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-red-200 bg-red-50 px-6 py-12 text-center">
        <p className="text-sm text-red-600">{errorMsg}</p>
        <button
          onClick={() => handleGenerate()}
          className="rounded-lg bg-brand-green px-4 py-2 text-sm font-medium text-white hover:opacity-90"
        >
          다시 시도
        </button>
      </div>
    );
  }

  // has_report
  return (
    <div>
      <div className="mb-3 flex justify-end">
        <button
          onClick={() => handleGenerate(true)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          새로 생성
        </button>
      </div>
      {report && <ReportView report={report} />}
    </div>
  );
}
