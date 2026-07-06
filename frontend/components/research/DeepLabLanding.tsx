const SECTIONS = [
  "사업구조",
  "재무 품질",
  "경쟁 구도",
  "자본배분",
  "실적/가이던스",
  "밸류에이션",
];

export function DeepLabLanding() {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm font-semibold text-slate-700 mb-3">리포트에 담기는 것</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {SECTIONS.map((section) => (
            <div
              key={section}
              className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-center text-sm font-medium text-slate-600"
            >
              {section}
            </div>
          ))}
        </div>
      </div>
      <p className="text-center text-xs text-slate-400">
        ⏱ 생성에 약 2~4분 소요 · SEC 10-K/10-Q/8-K 기반
      </p>
    </div>
  );
}
