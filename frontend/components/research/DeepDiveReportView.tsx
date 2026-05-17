"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface DeepDiveReportViewProps {
  markdown: string;
  onRefresh: () => void;
  isRefreshing: boolean;
}

const META_KEYWORDS = ["작성일", "대상 기간", "분석 근거", "작성자", "분석 대상"];

function extractTitle(raw: string): string {
  for (const line of raw.split("\n")) {
    const m = line.match(/^#{1,2}\s+(.+)/);
    if (m) return m[1].trim();
  }
  return "";
}

function prepareBody(raw: string): string {
  const lines = raw.split("\n");

  // Fix metadata line breaks
  const split = lines.flatMap((line) => {
    const hits = META_KEYWORDS.filter((k) => line.includes(k + ":")).length;
    if (hits > 1) {
      return line
        .replace(/\s+(작성일|대상 기간|분석 근거|작성자|분석 대상):/g, "\n\n$1:")
        .split("\n");
    }
    return [line];
  });

  // Ensure blank line between consecutive meta lines
  const result: string[] = [];
  split.forEach((line, i) => {
    result.push(line);
    const currIsMeta = META_KEYWORDS.some((k) => line.includes(k + ":"));
    const nextLine = split[i + 1] ?? "";
    const nextIsMeta =
      nextLine !== "" && META_KEYWORDS.some((k) => nextLine.includes(k + ":"));
    if (currIsMeta && nextIsMeta) result.push("");
  });

  return result.join("\n");
}

export function DeepDiveReportView({
  markdown,
  onRefresh,
  isRefreshing,
}: DeepDiveReportViewProps) {
  const title = extractTitle(markdown);
  const body = prepareBody(markdown);

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex justify-end items-center">
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-600 bg-white border border-slate-200 rounded-lg shadow-sm hover:bg-slate-50 hover:text-slate-900 disabled:opacity-50 transition-all"
        >
          <svg
            className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-[#22C55E]" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.253 8H18"
            />
          </svg>
          {isRefreshing ? "리포트 업데이트 중..." : "강제 새로고침"}
        </button>
      </div>

      <div className="bg-white border border-slate-100 rounded-xl shadow-sm overflow-hidden">
        {title && (
          <div className="px-6 md:px-8 pt-7 pb-5 border-b border-slate-100">
            <h2 className="text-xl font-bold text-slate-900 leading-snug">
              {title}
            </h2>
          </div>
        )}

        <div className="prose prose-slate max-w-none p-6 md:p-8">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: () => null,
              h2: () => null,
              table: ({ ...props }) => (
                <div className="overflow-x-auto my-6 border border-slate-100 rounded-lg">
                  <table
                    className="min-w-full divide-y divide-slate-200"
                    {...props}
                  />
                </div>
              ),
            }}
          >
            {body}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
