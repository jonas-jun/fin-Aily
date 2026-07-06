"use client";

/**
 * components/stock/StockTabNav.tsx
 * ─────────────────────────────────
 * 종목 페이지 상단 탭 네비게이션.
 *
 * 라우트 기반 탭:
 *   브리핑     → /stock/[symbol]           (기존 뉴스)
 *   심층 리서치 → /stock/[symbol]/research
 *
 * usePathname으로 활성 탭을 판별한다.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

interface Props {
  symbol: string;
}

const TAB_BASE =
  "px-1 pb-2 text-sm font-medium border-b-2 transition-colors -mb-px";

export function StockTabNav({ symbol }: Props) {
  const pathname = usePathname();
  const base = `/stock/${symbol}`;
  const isResearch = pathname?.endsWith("/research") ?? false;

  return (
    <nav className="mb-5 flex gap-6 border-b border-slate-200">
      <Link
        href={base}
        prefetch
        aria-current={!isResearch ? "page" : undefined}
        className={`${TAB_BASE} ${
          !isResearch
            ? "border-brand-green text-slate-900"
            : "border-transparent text-slate-400 hover:text-slate-600"
        }`}
      >
        브리핑
      </Link>
      <Link
        href={`${base}/research`}
        prefetch
        aria-current={isResearch ? "page" : undefined}
        className={`${TAB_BASE} ${
          isResearch
            ? "border-brand-green text-slate-900"
            : "border-transparent text-slate-400 hover:text-slate-600"
        }`}
      >
        심층 리서치
      </Link>
    </nav>
  );
}
