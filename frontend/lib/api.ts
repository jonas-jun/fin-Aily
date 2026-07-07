/**
 * lib/api.ts
 * ──────────
 * 백엔드 API 호출 유틸리티. 에러 파싱 통합.
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

export interface TickerResult {
  symbol: string;
  name: string;
  exchange?: string;
}

// ── 심층 리서치 ─────────────────────────────────────────────────────────────────
export interface ResearchJob {
  job_id: number;
  symbol: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: string | null;
  cached: boolean;
  report: string | null;
  error: string | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface ResearchSource {
  form_type: string;
  accession_no: string;
  url: string;
  report_date?: string;
}

export interface ResearchReport {
  symbol: string;
  status: string;
  report: string;
  sources: ResearchSource[] | null;
  model_version: string | null;
  created_at: string | null;
  completed_at: string | null;
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
  options: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });

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
    create: (symbol: string, opts?: { force?: boolean }): Promise<ResearchJob> =>
      apiFetch(`/research/${symbol}${opts?.force ? "?force=true" : ""}`, { method: "POST" }),
    get: (symbol: string): Promise<ResearchReport> =>
      apiFetch(`/research/${symbol}`),
    getJob: (jobId: number): Promise<ResearchJob> =>
      apiFetch(`/research/jobs/${jobId}`),
  },
};
