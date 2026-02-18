"use client";

/**
 * app/page.tsx
 * ─────────────
 * 홈 페이지: fin-aily 브랜드 및 탭 인터페이스 (Ticker Brief / Market Pulse).
 */

import { useState, useEffect } from "react";
import { TickerSearch } from "@/components/ui/TickerSearch";
import { DigestCard } from "@/components/news/DigestCard";
import { api, type NewsResponse } from "@/lib/api";

type TabType = "brief" | "pulse";

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<TabType>("brief");
  const [marketData, setMarketData] = useState<NewsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // Market Pulse 데이터 로드
  useEffect(() => {
    if (activeTab === "pulse" && !marketData) {
      const loadMarketPulse = async () => {
        setLoading(true);
        try {
          // 백엔드 엔드포인트: GET /news/market-pulse
          const data = await api.news.getMarketPulse();
          setMarketData(data);
        } catch (error) {
          console.error("Market Pulse 로드 오류:", error);
        } finally {
          setLoading(false);
        }
      };
      loadMarketPulse();
    }
  }, [activeTab, marketData]);

  return (
    <div className="flex min-h-[70vh] flex-col items-center pt-16 md:pt-24 gap-10 px-4">
      {/* 히어로 섹션 */}
      <div className="text-center space-y-3">
        <div className="text-4xl sm:text-5xl mb-4">📈</div>
        <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">fin-Aily</h1>
        <p className="text-slate-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed">
          {activeTab === "brief" 
            ? "티커를 검색하면 AI가 최신 뉴스를 10개의 핵심 포인트로 요약해드립니다." 
            : "최신 주요 경제 소식을 AI 비서가 정리해드립니다."}
        </p>
      </div>

      {/* 탭 네비게이션 */}
      <div className="flex p-1.5 bg-slate-100 rounded-2xl w-full max-w-[340px] border border-slate-200/50 shadow-inner">
        <button
          onClick={() => setActiveTab("brief")}
          className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
            activeTab === "brief" 
              ? "bg-white text-blue-600 shadow-md" 
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          Ticker Brief
        </button>
        <button
          onClick={() => setActiveTab("pulse")}
          className={`flex-1 py-2.5 text-sm font-bold rounded-xl transition-all ${
            activeTab === "pulse" 
              ? "bg-white text-blue-600 shadow-md" 
              : "text-slate-500 hover:text-slate-800"
          }`}
        >
          Market Pulse
        </button>
      </div>

      {/* 콘텐츠 영역 */}
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
                  <div className="absolute inset-0 border-4 border-blue-100 rounded-full"></div>
                  <div className="absolute inset-0 border-4 border-blue-600 rounded-full border-t-transparent animate-spin"></div>
                </div>
                <p className="text-slate-500 font-medium animate-pulse">AI 비서가 최신 뉴스를 분석하고 있습니다...</p>
              </div>
            ) : marketData ? (
              <DigestCard digest={marketData.digest} symbol="MARKET" articles={marketData.articles} />
            ) : (
              <div className="py-20 border-2 border-dashed border-slate-200 rounded-3xl text-center">
                <p className="text-slate-400">시장의 맥박을 불러올 수 없습니다. 다시 시도해주세요.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}