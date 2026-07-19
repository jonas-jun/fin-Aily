"use client";

/**
 * app/stock/[symbol]/page.tsx
 * ─────────────────────────────
 * 종목 뉴스 페이지.
 *
 * 레이아웃:
 *   1. DigestCard  — AI 종합 요약 + Sentiment (상단)
 *   2. ArticleList — 기사 제목/링크 목록 (하단)
 */

import { useCallback } from "react";
import { useParams } from "next/navigation";
import { api, type NewsResponse } from "@/lib/api";
import { TickerDigestCard } from "@/components/news/DigestCard";
import { ArticleList } from "@/components/news/ArticleList";
import { NewsPageSkeleton } from "@/components/ui/Skeletons";
import { timeAgo } from "@/lib/utils";
import { useAsync } from "@/lib/hooks/useAsync";

export default function StockNewsPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const upper = symbol?.toUpperCase() ?? "";

  const loadNews = useCallback((): Promise<NewsResponse> => api.news.get(upper), [upper]);
  const result = useAsync(loadNews, [upper], { enabled: Boolean(upper) });
  const data = result.status === "success" ? result.data : null;

  return (
    <div>
      {/* 페이지 헤더 */}
      <div className="mb-6">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-3">
          <h1 className="text-xl sm:text-2xl font-bold text-slate-900">{upper}</h1>
          {data && <span className="text-sm sm:text-base text-slate-500">{data.company_name}</span>}
        </div>
        {data && (
          <p className="text-xs text-slate-400 mt-1">
            마지막 업데이트: {timeAgo(data.last_updated)}
          </p>
        )}
      </div>

      {/* 로딩 */}
      {(result.status === "idle" || result.status === "loading") && <NewsPageSkeleton />}

      {/* 에러 */}
      {result.status === "error" && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          {result.error}
        </div>
      )}

      {/* 정상 */}
      {data && (
        <>
          <TickerDigestCard digest={data.digest} />
          <ArticleList articles={data.articles} />
        </>
      )}
    </div>
  );
}
