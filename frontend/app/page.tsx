"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { DigestCard } from "@/components/news/DigestCard";
import { Logo } from "@/components/ui/Logo";
import { api, type NewsResponse } from "@/lib/api";

type TabType = "brief" | "deepdive" | "pulse";

const TABS: { id: TabType; label: string; description: string }[] = [
  {
    id: "brief",
    label: "Ticker Brief",
    description: "Get 10 AI-powered news highlights for any ticker.",
  },
  {
    id: "deepdive",
    label: "Deep Dive",
    description: "In-depth analysis based on SEC filings & earnings calls.",
  },
  {
    id: "pulse",
    label: "Market Pulse",
    description: "Your AI assistant curates today's top market headlines.",
  },
];

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tabParam = searchParams.get("tab");
  const activeTab: TabType =
    tabParam === "deepdive" ? "deepdive" : tabParam === "pulse" ? "pulse" : "brief";

  const [marketData, setMarketData] = useState<NewsResponse | null>(null);
  const [pulseLoading, setPulseLoading] = useState(false);

  const setActiveTab = (tab: TabType) => {
    if (tab === "brief") router.push("/");
    else router.push(`/?tab=${tab}`);
  };

  useEffect(() => {
    if (activeTab === "pulse" && !marketData) {
      setPulseLoading(true);
      api.news
        .getMarketPulse()
        .then((data) => setMarketData(data))
        .catch((err) => console.error("Market Pulse load error:", err))
        .finally(() => setPulseLoading(false));
    }
  }, [activeTab, marketData]);

  const currentTab = TABS.find((t) => t.id === activeTab)!;

  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      {/* Hero */}
      <div className="text-center space-y-3">
        <Logo size="lg" />
        <p className="text-slate-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed mt-4">
          {currentTab.description}
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex p-1.5 bg-slate-100 rounded-2xl w-full max-w-[460px] border border-slate-200/50 shadow-inner">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
              activeTab === tab.id
                ? "bg-white text-[#22C55E] shadow-md"
                : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="w-full max-w-2xl">
        {activeTab === "brief" && (
          <div className="flex flex-col items-center animate-in fade-in zoom-in-95">
            <TickerSearch />
          </div>
        )}

        {activeTab === "deepdive" && (
          <div className="flex flex-col items-center animate-in fade-in zoom-in-95">
            <TickerSearch
              placeholder="Enter ticker for deep analysis (e.g. AAPL, NVDA)"
              onSelect={(sym) => router.push(`/stock/${sym}?tab=deepdive`)}
            />
          </div>
        )}

        {activeTab === "pulse" && (
          <div className="animate-in fade-in slide-in-from-bottom-4 space-y-10">
            {pulseLoading ? (
              <div className="py-24 text-center space-y-5">
                <div className="relative w-12 h-12 mx-auto">
                  <div className="absolute inset-0 border-4 border-green-100 rounded-full" />
                  <div className="absolute inset-0 border-4 border-[#22C55E] rounded-full border-t-transparent animate-spin" />
                </div>
                <p className="text-slate-500 font-medium animate-pulse">
                  AI is analyzing the latest news...
                </p>
              </div>
            ) : marketData ? (
              <DigestCard digest={marketData.digest} symbol="MARKET" articles={marketData.articles} />
            ) : (
              <div className="py-20 border-2 border-dashed border-slate-200 rounded-3xl text-center">
                <p className="text-slate-400">Unable to load market pulse. Please try again.</p>
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
