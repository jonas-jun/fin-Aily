"use client";

/**
 * components/research/DeepResearchView.tsx
 * ─────────────────────────────────────────
 * 심층 리서치 상태에 따른 화면을 렌더링한다.
 *
 *   loading   ─(GET latest)─▶ has_report  : ReportView + "새로 생성"
 *                          └▶ 404(7일 이내 리포트 없음) → 자동 POST create
 *   POST create ─▶ cached/completed → GET latest → has_report
 *               └▶ job(pending)     → polling
 *   polling ─(5초 setTimeout 재귀)─▶ completed → GET latest → has_report
 *                                 └▶ failed    → error + "다시 시도"
 *
 * 폴링과 요청 취소는 useDeepResearch가 담당한다.
 */

import { useDeepResearch } from "@/lib/hooks/useDeepResearch";
import { ReportView } from "./ReportView";
import { ResearchProgress } from "./ResearchProgress";

interface Props {
  symbol: string;
}

export function DeepResearchView({ symbol }: Props) {
  const { state, retry, regenerate } = useDeepResearch(symbol);

  // ── 렌더 ────────────────────────────────────────────────────────────────────
  if (state.phase === "loading") {
    return (
      <div className="flex items-center justify-center py-16 text-sm text-slate-400">
        불러오는 중…
      </div>
    );
  }

  if (state.phase === "generating") {
    return <ResearchProgress progress={state.job?.progress ?? null} startedAt={state.startedAt} />;
  }

  if (state.phase === "error") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-xl border border-red-200 bg-red-50 px-6 py-12 text-center">
        <p className="text-sm text-red-600">{state.message}</p>
        <button
          onClick={retry}
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
          onClick={regenerate}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
        >
          새로 생성
        </button>
      </div>
      <ReportView report={state.report} />
    </div>
  );
}
