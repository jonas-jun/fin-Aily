"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { DigestCard } from "@/components/news/DigestCard";
import { Logo } from "@/components/ui/Logo";
import { api, type NewsResponse } from "@/lib/api";

type TabType = "brief" | "pulse";

function HomeContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab: TabType = searchParams.get("tab") === "pulse" ? "pulse" : "brief";

  const [marketData, setMarketData] = useState<NewsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const setActiveTab = (tab: TabType) => {
    router.push(tab === "pulse" ? "/?tab=pulse" : "/");
  };

  useEffect(() => {
    if (activeTab === "pulse" && !marketData) {
      const loadMarketPulse = async () => {
        setLoading(true);
        try {
          const data = await api.news.getMarketPulse();
          setMarketData(data);
        } catch (error) {
          console.error("Market Pulse load error:", error);
        } finally {
          setLoading(false);
        }
      };
      loadMarketPulse();
    }
  }, [activeTab, marketData]);

  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      {/* Hero */}
      <div className="text-center space-y-3">
        <Logo size="lg" />
        <p className="text-slate-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed mt-4">
          {activeTab === "brief"
            ? "Get 10 AI-powered news highlights for any ticker."
            : "Your AI assistant curates today's top market headlines."}
        </p>
      </div>

      {/* Tab navigation */}
      <div className="flex p-1.5 bg-slate-100 rounded-2xl w-full max-w-[340px] border border-slate-200/50 shadow-inner">
        <button
          onClick={() => setActiveTab("brief")}
          className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
            activeTab === "brief"
              ? "bg-white text-[#22C55E] shadow-md"
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          Ticker Brief
        </button>
        <button
          onClick={() => setActiveTab("pulse")}
          className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
            activeTab === "pulse"
              ? "bg-white text-[#22C55E] shadow-md"
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          Market Pulse
        </button>
      </div>

      {/* Content */}
      <div className="w-full max-w-2xl transition-all duration-500 ease-in-out">
        {activeTab === "brief" ? (
          <div className="flex flex-col items-center gap-8 animate-in fade-in zoom-in-95">
            <TickerSearch />
          </div>
        ) : (
          <div className="animate-in fade-in slide-in-from-bottom-4 space-y-10">
            {loading ? (
              <div className="py-24 text-center space-y-5">
                <div className="relative w-12 h-12 mx-auto">
                  <div className="absolute inset-0 border-4 border-green-100 rounded-full"></div>
                  <div className="absolute inset-0 border-4 border-[#22C55E] rounded-full border-t-transparent animate-spin"></div>
                </div>
                <p className="text-slate-500 font-medium animate-pulse">AI is analyzing the latest news...</p>
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
