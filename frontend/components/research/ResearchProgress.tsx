"use client";

/**
 * components/research/ResearchProgress.tsx
 * ─────────────────────────────────────────
 * 리포트 생성 진행 표시.
 * 서버의 progress 문자열 + 경과 시간 + 스피너.
 */

import { useEffect, useState } from "react";
import { Spinner } from "@/components/ui/Spinner";

interface Props {
  /** 서버가 반환한 진행 문구 (예: "리포트 생성 중") */
  progress: string | null;
  /** 폴링 시작 시각 (경과 시간 계산용) */
  startedAt: number;
}

function formatElapsed(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}분 ${s}초` : `${s}초`;
}

export function ResearchProgress({ progress, startedAt }: Props) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const tick = () => setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-6 py-12 text-center">
      <Spinner className="border-slate-200" />
      <p className="text-sm font-medium text-slate-700">
        {progress || "리포트 생성 중"}
      </p>
      <p className="text-xs text-slate-400">
        경과 {formatElapsed(elapsed)} · 보통 2~4분 정도 걸립니다
      </p>
    </div>
  );
}
