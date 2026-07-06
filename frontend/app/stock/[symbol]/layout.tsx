"use client";

/**
 * app/stock/[symbol]/layout.tsx
 * ──────────────────────────────
 * 종목 페이지 공통 레이아웃.
 *
 * 탭바(<StockTabNav>)만 소유하고 {children}을 렌더한다.
 * 데이터 페칭은 각 page.tsx가 자체적으로 하므로 레이아웃은 얇게 유지 —
 * 브리핑/리서치가 서로의 로딩·에러 상태에 얽히지 않는다.
 */

import { useParams } from "next/navigation";
import { StockTabNav } from "@/components/stock/StockTabNav";

export default function StockLayout({ children }: { children: React.ReactNode }) {
  const { symbol } = useParams<{ symbol: string }>();
  const upper = symbol?.toUpperCase() ?? "";

  return (
    <div>
      <StockTabNav symbol={upper} />
      {children}
    </div>
  );
}
