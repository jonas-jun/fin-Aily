"use client";

import { useEffect, useState, useCallback, Suspense } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { api, type NewsResponse, type DeepDiveResponse } from "@/lib/api";
import { DigestCard } from "@/components/news/DigestCard";
import { ArticleList } from "@/components/news/ArticleList";
import { NewsPageSkeleton } from "@/components/ui/Skeletons";
import { timeAgo } from "@/lib/utils";
import { DeepDiveLoading } from "@/components/research/DeepDiveLoading";
import { DeepDiveReportView } from "@/components/research/DeepDiveReportView";
import { SourceMetadataCard } from "@/components/research/SourceMetadataCard";

type TabType = "news" | "deepdive";

function StockDetailContent() {
  const { symbol } = useParams<{ symbol: string }>();
  const searchParams = useSearchParams();
  const upperSymbol = symbol?.toUpperCase() ?? "";

  const activeTab: TabType =
    searchParams.get("tab") === "deepdive" ? "deepdive" : "news";

  const [newsData, setNewsData] = useState<NewsResponse | null>(null);
  const [newsLoading, setNewsLoading] = useState(true);
  const [newsError, setNewsError] = useState<string | null>(null);

  const [deepDiveData, setDeepDiveData] = useState<DeepDiveResponse | null>(null);
  const [deepDiveLoading, setDeepDiveLoading] = useState(false);
  const [deepDiveError, setDeepDiveError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (!upperSymbol) return;
    let cancelled = false;

    const fetchNews = async () => {
      setNewsLoading(true);
      setNewsError(null);
      try {
        const res = await api.news.get(upperSymbol);
        if (!cancelled) setNewsData(res);
      } catch (err: unknown) {
        if (!cancelled)
          setNewsError(err instanceof Error ? err.message : "뉴스를 가져오는 데 실패했습니다.");
      } finally {
        if (!cancelled) setNewsLoading(false);
      }
    };

    fetchNews();
    return () => { cancelled = true; };
  }, [upperSymbol]);

  const fetchDeepDive = useCallback(async (force = false) => {
    if (!upperSymbol) return;
    if (deepDiveData && !force) return;

    let cancelled = false;

    if (force) setIsRefreshing(true);
    else setDeepDiveLoading(true);
    setDeepDiveError(null);

    try {
      const res = await api.research.get(upperSymbol, force);
      if (!cancelled) setDeepDiveData(res);
    } catch (err: unknown) {
      if (!cancelled)
        setDeepDiveError(
          err instanceof Error
            ? err.message
            : "심층 분석 리포트를 생성하는 과정에서 오류가 발생했습니다.",
        );
    } finally {
      if (!cancelled) {
        setDeepDiveLoading(false);
        setIsRefreshing(false);
      }
    }

    return () => { cancelled = true; };
  }, [upperSymbol, deepDiveData]);

  useEffect(() => {
    if (activeTab === "deepdive") {
      fetchDeepDive();
    }
  }, [activeTab, fetchDeepDive]);

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-6">
      <div className="flex justify-between items-baseline border-b border-slate-100 pb-4">
        <div className="flex items-baseline gap-3">
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">{upperSymbol}</h1>
          {newsData && <span className="text-lg text-slate-500 font-medium">{newsData.company_name}</span>}
        </div>
        <p className="text-xs text-slate-400 font-mono">
          {activeTab === "news" && newsData && `Last updated: ${timeAgo(newsData.last_updated)}`}
          {activeTab === "deepdive" && deepDiveData && `Report generated: ${timeAgo(deepDiveData.generated_at)}`}
        </p>
      </div>


      <div className="min-h-[400px]">
        {activeTab === "news" ? (
          <>
            {newsLoading && <NewsPageSkeleton />}
            {!newsLoading && newsError && (
              <div className="text-sm text-red-500 bg-red-50 p-4 border border-red-200 rounded-lg">
                {newsError}
              </div>
            )}
            {!newsLoading && newsData && (
              <div className="space-y-6">
                <DigestCard digest={newsData.digest} />
                <ArticleList articles={newsData.articles} />
              </div>
            )}
          </>
        ) : (
          <>
            {deepDiveLoading && <DeepDiveLoading />}

            {!deepDiveLoading && deepDiveError && (
              <div className="text-sm text-red-500 bg-red-50 p-4 border border-red-200 rounded-lg shadow-sm">
                <p className="font-semibold mb-1">리포트 로드 실패</p>
                <p>{deepDiveError}</p>
                <button
                  onClick={() => fetchDeepDive(true)}
                  className="mt-3 px-3 py-1.5 bg-white border border-red-300 rounded-md text-xs font-bold hover:bg-red-100 transition-colors"
                >
                  다시 시도하기
                </button>
              </div>
            )}

            {!deepDiveLoading && deepDiveData && (
              <div className="space-y-6">
                <DeepDiveReportView
                  markdown={deepDiveData.report_markdown}
                  onRefresh={() => fetchDeepDive(true)}
                  isRefreshing={isRefreshing}
                />
                <SourceMetadataCard
                  metadata={deepDiveData.source_metadata}
                  modelVersion={deepDiveData.model_version}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function StockDetailPage() {
  return (
    <Suspense>
      <StockDetailContent />
    </Suspense>
  );
}
