"use client";

import { useState, useEffect } from "react";

const LOADING_STEPS = [
  "SEC EDGAR 시스템에서 최신 공시 문서(10-K, 10-Q)를 수집하고 있습니다...",
  "최신 분기 어닝스콜 질의응답(Q&A) 스크립트를 다운로드하는 중입니다...",
  "수집된 대용량 금융 컨텍스트 청크를 정제하고 매핑하고 있습니다 (Map 단계)...",
  "AI 애널리스트가 재무 지표 및 미래 가이던스를 종합 분석 중입니다 (Reduce 단계)...",
  "기관투자자급 종합 Deep Dive 리포트를 마크다운으로 최종 편집하고 있습니다...",
];

export function DeepDiveLoading() {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStepIndex((prev) => (prev < LOADING_STEPS.length - 1 ? prev + 1 : prev));
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="py-24 flex flex-col items-center justify-center text-center space-y-6 max-w-md mx-auto animate-in fade-in duration-500">
      <div className="relative w-14 h-14">
        <div className="absolute inset-0 border-4 border-emerald-100 rounded-full"></div>
        <div className="absolute inset-0 border-4 border-t-[#22C55E] rounded-full animate-spin"></div>
      </div>
      <div className="space-y-2">
        <p className="text-sm font-semibold text-slate-800">금융 데이터 인텔리전스 가동 중</p>
        <p className="text-xs text-slate-500 leading-relaxed min-h-[40px] px-4 font-medium transition-all duration-500">
          {LOADING_STEPS[stepIndex]}
        </p>
      </div>
      <p className="text-[10px] text-slate-400">
        최초 생성 시 최대 1~2분이 소요될 수 있으며, 완료 후 7일간 캐싱됩니다.
      </p>
    </div>
  );
}
