"use client";

/**
 * components/research/ReportView.tsx
 * ──────────────────────────────────
 * 완료된 심층 리서치 리포트(Markdown)를 렌더링한다.
 *
 * - react-markdown + remark-gfm(표) + rehype-raw(목차 <a id> 앵커·표 셀 <br>).
 * - 리포트는 자사 파이프라인 산출물만 렌더하므로 raw HTML 허용이 안전하다.
 * - 목차는 리포트 마크다운에 이미 포함되어 있어 별도 구현하지 않는다.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import type { ResearchReport } from "@/lib/api";
import { timeAgo, formatDate } from "@/lib/utils";

interface Props {
  report: ResearchReport;
}

export function ReportView({ report }: Props) {
  const generatedAt = report.completed_at ?? report.created_at ?? "";

  return (
    <article>
      {/* 메타 헤더 */}
      <div className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
        {generatedAt && (
          <span>
            생성:{" "}
            <time dateTime={generatedAt} title={formatDate(generatedAt)}>
              {timeAgo(generatedAt)}
            </time>
          </span>
        )}
        {report.model_version && (
          <>
            <span>·</span>
            <span className="font-mono">{report.model_version}</span>
          </>
        )}
      </div>

      {/* 리포트 본문 — 표는 가로 스크롤 래퍼로 감싼다 */}
      <div
        className="prose prose-slate max-w-none prose-sm sm:prose-base
                   prose-headings:scroll-mt-20 prose-headings:font-semibold
                   prose-a:text-brand-green prose-a:no-underline hover:prose-a:underline
                   prose-table:overflow-x-auto"
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw]}
          components={{
            // 넓은 표가 페이지를 밀지 않도록 각 표를 개별 스크롤 컨테이너로 감싼다.
            table: (props) => (
              <div className="overflow-x-auto">
                <table {...props} />
              </div>
            ),
          }}
        >
          {report.report}
        </ReactMarkdown>
      </div>
    </article>
  );
}
