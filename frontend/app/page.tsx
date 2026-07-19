"use client";

import { useCallback, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { MarketPulseCard } from "@/components/news/DigestCard";
import { DeepLabLanding } from "@/components/research/DeepLabLanding";
import { Logo } from "@/components/ui/Logo";
import { api, type NewsResponse } from "@/lib/api";
import { Spinner } from "@/components/ui/Spinner";
import { useAsync } from "@/lib/hooks/useAsync";

type TabType = "brief" | "pulse" | "research";

const TABS: { key: TabType; label: string; description: string }[] = [
  {
    key: "brief",
    label: "Ticker Brief",
    description: "Get 10 AI-powered news highlights for any ticker.",
  },
  {
    key: "pulse",
    label: "Market Pulse",
    description: "Your AI assistant curates today's top market headlines.",
  },
  {
    key: "research",
    label: "Deep Lab",
    description: "SEC 공시를 분석해 종목별 심층 리서치 리포트를 생성합니다.",
  },
];

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const activeTab: TabType =
    tabParam === "pulse" ? "pulse" : tabParam === "research" ? "research" : "brief";

  const loadMarketPulse = useCallback((): Promise<NewsResponse> => api.news.getMarketPulse(), []);
  const market = useAsync(loadMarketPulse, [], {
    enabled: activeTab === "pulse",
    retainSuccess: true,
  });

  const setActiveTab = (tab: TabType) => {
    router.push(tab === "brief" ? "/" : `/?tab=${tab}`);
  };

  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      {/* Hero */}
      <div className="text-center space-y-3">
        <Logo size="lg" />
        <p className="text-slate-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed mt-4">
          {TABS.find((tab) => tab.key === activeTab)?.description}
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex p-1.5 bg-slate-100 rounded-2xl w-full max-w-[340px] border border-slate-200/50 shadow-inner">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
              activeTab === key
                ? "bg-white text-brand-green shadow-md"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="w-full max-w-2xl transition-all duration-500 ease-in-out">
        {activeTab === "brief" ? (
          <div className="flex flex-col items-center gap-8 animate-in fade-in zoom-in-95">
            <TickerSearch />
          </div>
        ) : activeTab === "research" ? (
          <div className="flex flex-col items-center gap-8 animate-in fade-in zoom-in-95">
            <TickerSearch destination="research" />
            <DeepLabLanding />
          </div>
        ) : (
          <div className="animate-in fade-in slide-in-from-bottom-4 space-y-10">
            {market.status === "loading" || market.status === "idle" ? (
              <div className="py-24 text-center space-y-5">
                <Spinner size="lg" />
                <p className="text-slate-500 font-medium animate-pulse">AI is analyzing the latest news...</p>
              </div>
            ) : market.status === "success" ? (
              <MarketPulseCard digest={market.data.digest} articles={market.data.articles} />
            ) : (
              <div className="py-20 border-2 border-dashed border-slate-200 rounded-3xl text-center">
                <p className="text-slate-400">{market.error || "Unable to load market pulse. Please try again."}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function HomePage() {
  return (
    <Suspense>
      <HomeContent />
    </Suspense>
  );
}
