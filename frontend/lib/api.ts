/**
 * lib/api.ts
 * ──────────
 * 백엔드 API 호출 유틸리티.
 * 인증 토큰 자동 첨부, 에러 파싱 통합.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/v1";

// ── 타입 ──────────────────────────────────────────────────────────────────────
export interface Sentiment {
  score: number;
  label: "Positive" | "Neutral" | "Negative";
}

export interface SummaryPoint {
  point: string;
  quote: string;
}

export interface Digest {
  summary: SummaryPoint[];
  sentiment: Sentiment;
  based_on_articles: number;
}

export interface Article {
  id: number;
  title: string;
  source: string;
  url: string;
  published_at: string;
}

export interface NewsResponse {
  symbol: string;
  company_name: string;
  last_updated: string;
  digest: Digest;
  articles: Article[];
}

export interface SourceFiling {
  form: string;
  fiscal_year: number;
  fiscal_quarter: number | null;
  filing_date: string;
  period_of_report: string;
  doc_id: string;
}

export interface SourceCall {
  fiscal_year: number;
  fiscal_quarter: number;
  event_date: string;
  source: string;
  source_url: string;
}

export interface DeepDiveResponse {
  symbol: string;
  company_name: string;
  generated_at: string;
  model_version: string;
  report_markdown: string;
  source_metadata: {
    ticker: string;
    analysis_period: string;
    sources: {
      sec_filings: SourceFiling[];
      earning_calls: SourceCall[];
    };
  };
}

export interface TickerResult {
  symbol: string;
  name: string;
  exchange?: string;
}

export interface UserProfile {
  id: string;
  email: string;
  display_name: string | null;
  preferred_language: "ko" | "en";
  created_at: string;
}

// ── API 에러 ──────────────────────────────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── 내부 fetch 래퍼 ───────────────────────────────────────────────────────────
async function apiFetch<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const { token, ...fetchOptions } = options;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(fetchOptions.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE_URL}${path}`, { ...fetchOptions, headers });

  if (!res.ok) {
    let code = "UNKNOWN_ERROR";
    let message = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      code = body?.detail?.code ?? body?.error?.code ?? code;
      message = body?.detail?.message ?? body?.error?.message ?? message;
    } catch {}
    throw new ApiError(code, message, res.status);
  }

  return res.json() as Promise<T>;
}

// ── 공개 API ──────────────────────────────────────────────────────────────────
export const api = {
  tickers: {
    search: (q: string): Promise<{ results: TickerResult[] }> =>
      apiFetch(`/tickers/search?q=${encodeURIComponent(q)}`),
  },

  news: {
    get: (symbol: string, lang = "ko", limit = 10): Promise<NewsResponse> =>
      apiFetch(`/news/${symbol}?lang=${lang}&limit=${limit}`),
    getMarketPulse: (lang = "ko"): Promise<NewsResponse> =>
      apiFetch(`/news/market-pulse?lang=${lang}`),
  },

  research: {
    get: (symbol: string, forceRefresh = false): Promise<DeepDiveResponse> =>
      apiFetch(`/research/${symbol}${forceRefresh ? "?force_refresh=true" : ""}`),
  },

  users: {
    me: (token: string): Promise<UserProfile> =>
      apiFetch("/users/me", { token }),

    update: (
      token: string,
      body: { display_name?: string; preferred_language?: string },
    ): Promise<UserProfile> =>
      apiFetch("/users/me", { method: "PATCH", body: JSON.stringify(body), token }),
  },
};
