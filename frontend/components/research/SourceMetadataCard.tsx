"use client";

import { useState } from "react";
import { type DeepDiveResponse } from "@/lib/api";

interface SourceMetadataCardProps {
  metadata: DeepDiveResponse["source_metadata"];
  modelVersion: string;
}

export function SourceMetadataCard({ metadata, modelVersion }: SourceMetadataCardProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="bg-slate-50 border border-slate-200/60 rounded-xl overflow-hidden transition-all duration-200">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex justify-between items-center p-4 text-left text-xs font-bold text-slate-700 hover:bg-slate-100/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg className="w-4 h-4 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5l5 5v11a2 2 0 01-2 2z" />
          </svg>
          <span>AI 분석 데이터 소스 및 투명성 리포트</span>
        </div>
        <svg
          className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="p-4 border-t border-slate-200/60 bg-white space-y-4 text-xs text-slate-600 animate-in slide-in-from-top-2 duration-200">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 border-b border-slate-100 pb-3">
            <div>
              <span className="font-semibold text-slate-400">분석 대상 기간: </span>
              {metadata.analysis_period}
            </div>
            <div>
              <span className="font-semibold text-slate-400">추론 프레임워크 모델: </span>
              {modelVersion}
            </div>
          </div>

          <div className="space-y-3">
            <div>
              <p className="font-bold text-slate-800 mb-1.5">1. 매핑된 SEC 공시서류 (EDGAR)</p>
              <div className="bg-slate-50 rounded-lg p-2.5 max-h-40 overflow-y-auto space-y-1">
                {metadata.sources.sec_filings.map((f, idx) => (
                  <div
                    key={idx}
                    className="flex justify-between font-mono text-[11px] text-slate-600 py-0.5 border-b border-slate-100 last:border-0"
                  >
                    <span>Form {f.form} ({f.fiscal_year}Y {f.fiscal_quarter ? `Q${f.fiscal_quarter}` : ""})</span>
                    <span className="text-slate-400">공시일: {f.filing_date}</span>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="font-bold text-slate-800 mb-1.5">2. 매핑된 실적 어닝스콜 (Earnings Call)</p>
              <div className="bg-slate-50 rounded-lg p-2.5 max-h-40 overflow-y-auto space-y-1">
                {metadata.sources.earning_calls.map((c, idx) => (
                  <div
                    key={idx}
                    className="flex justify-between items-center text-[11px] text-slate-600 py-1 border-b border-slate-100 last:border-0"
                  >
                    <span>{c.fiscal_year}년 Q{c.fiscal_quarter} 실적 컨퍼런스 콜 ({c.event_date})</span>
                    <a
                      href={c.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-emerald-600 hover:underline font-medium flex items-center gap-0.5 shrink-0"
                    >
                      원문보기
                      <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                      </svg>
                    </a>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
