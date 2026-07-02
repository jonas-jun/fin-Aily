"use client";

/**
 * app/stock/[symbol]/research/page.tsx
 * ─────────────────────────────────────
 * 심층 리서치 탭. URL: /stock/[symbol]/research
 *
 * 얇은 진입점 — 상태 머신과 렌더는 <DeepResearchView>가 담당한다.
 */

import { useParams } from "next/navigation";
import { DeepResearchView } from "@/components/research/DeepResearchView";

export default function StockResearchPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const upper = symbol?.toUpperCase() ?? "";

  return (
    <div>
      <h1 className="mb-4 text-xl sm:text-2xl font-bold text-slate-900">
        {upper} <span className="text-sm font-normal text-slate-400">심층 리서치</span>
      </h1>
      {upper && <DeepResearchView symbol={upper} />}
    </div>
  );
}
