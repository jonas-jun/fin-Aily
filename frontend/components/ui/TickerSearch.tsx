"use client";

/**
 * components/ui/TickerSearch.tsx
 * ────────────────────────────────
 * 티커 자동완성 검색 컴포넌트.
 */

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type TickerResult } from "@/lib/api";

export function TickerSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<TickerResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // 디바운스 검색
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (query.trim().length < 1) {
      setResults([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { results } = await api.tickers.search(query.trim());
        setResults(results);
        setOpen(results.length > 0);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
  }, [query]);

  const handleSelect = (symbol: string) => {
    setQuery("");
    setOpen(false);
    router.push(`/stock/${symbol}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) handleSelect(query.trim().toUpperCase());
  };

  return (
    <div ref={containerRef} className="relative w-full max-w-lg">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="티커 검색 (예: AAPL, TSLA)"
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-3 sm:py-2.5 text-base sm:text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          {loading && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 text-xs">
              검색 중…
            </span>
          )}
        </div>
        <button
          type="submit"
          className="rounded-lg bg-blue-600 px-4 py-3 sm:py-2.5 text-base sm:text-sm font-medium text-white hover:bg-blue-700 active:bg-blue-800 transition-colors"
        >
          검색
        </button>
      </form>

      {/* 자동완성 드롭다운 */}
      {open && (
        <ul className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 bg-white shadow-lg">
          {results.map((r) => (
            <li key={r.symbol}>
              <button
                type="button"
                onClick={() => handleSelect(r.symbol)}
                className="flex w-full items-center justify-between px-4 py-3 sm:py-2.5 text-left text-sm hover:bg-slate-50 active:bg-slate-100 transition-colors"
              >
                <span className="font-semibold text-slate-900">{r.symbol}</span>
                <span className="text-slate-500 truncate max-w-[200px]">{r.name}</span>
                {r.exchange && (
                  <span className="ml-2 text-xs text-slate-400 shrink-0">{r.exchange}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
