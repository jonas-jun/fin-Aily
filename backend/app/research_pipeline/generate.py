from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .research_config import PROMPTS_DIR, AppConfig, load_config
from .assemble import assemble_report
from .edgar import EdgarBundle, FilingRecord, SecClient, fiscal_label
from .factpack import FactPack, build_factpack
from .financials import build_financial_bundle
from .llm import GeminiClient, gather_limited
from .sections import (
    QA_SCHEMA,
    SECTION_SPECS,
    STR,
    SectionSpec,
    arr_obj,
    fallback_section,
    get_section,
    obj,
    wave_sections,
)

GUIDANCE_EXTRACT_SCHEMA = obj(
    {
        "period_label": STR,
        "revenue_actual": STR,
        "eps_actual": STR,
        "guidance_items": arr_obj({"metric": STR, "period": STR, "stated": STR}),
    }
)
from .utils import (
    bullet_list,
    ensure_dir,
    read_json,
    render_template,
    simple_summary,
    trim_text,
    utc_now_iso,
    write_json,
)


@dataclass(frozen=True)
class GenerateOptions:
    ticker: str
    output_path: Path | None = None
    section: int | None = None
    dump: bool = True
    use_llm: bool = True
    run_qa: bool = False


class ResearchPipeline:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or load_config()
        self.llm = GeminiClient(self.config.gemini_api_key)
        self.prompts_dir = PROMPTS_DIR

    async def run(self, options: GenerateOptions) -> Path:
        ticker = options.ticker.upper().strip()
        output_path = options.output_path or self.config.output_dir / f"{ticker}.md"
        output_path = output_path.expanduser()
        if not output_path.is_absolute():
            output_path = Path.cwd() / output_path
        ensure_dir(output_path.parent)
        artifact_dir = output_path.parent / f"{output_path.stem}_artifacts"

        sec = SecClient(self.config.edgar_user_agent, self.config.cache_dir / "sec")
        edgar = sec.collect_company_bundle(ticker)
        companyfacts = None
        if edgar.identity.cik is not None:
            try:
                companyfacts = sec.companyfacts(edgar.identity.cik)
            except Exception as exc:
                edgar.errors.append(f"SEC companyfacts 수집 실패: {exc}")

        financials = build_financial_bundle(ticker, edgar.identity, companyfacts)
        factpack = build_factpack(edgar, financials)
        summaries = await self._build_summaries(ticker, edgar, options.use_llm)
        guidance_vs_actual = await self._build_guidance_table(ticker, edgar, options.use_llm)
        base_context = self._build_base_context(ticker, edgar, factpack, summaries, guidance_vs_actual)

        sections = self._load_existing_sections(artifact_dir) if options.section else {}
        target_specs = self._target_specs(options.section, sections)

        wave1_specs = [spec for spec in target_specs if spec.wave == 1]
        if wave1_specs:
            generated_wave1 = await gather_limited(
                self._max_concurrency(),
                *(self._generate_section(spec, base_context, options.use_llm) for spec in wave1_specs),
            )
            sections.update({spec.number: payload for spec, payload in generated_wave1})

        if not options.section or (options.section in (1, 10) and not self._has_wave1_takeaways(sections)):
            missing_wave1 = [spec for spec in wave_sections(1) if spec.number not in sections]
            if missing_wave1:
                generated_wave1 = await gather_limited(
                    self._max_concurrency(),
                    *(self._generate_section(spec, base_context, options.use_llm) for spec in missing_wave1),
                )
                sections.update({spec.number: payload for spec, payload in generated_wave1})

        wave_context = base_context | {"wave1_takeaways": self._format_takeaways(sections)}
        wave2_specs = [spec for spec in target_specs if spec.wave == 2]
        if not options.section:
            wave2_specs = wave_sections(2)
        if wave2_specs:
            generated_wave2 = await gather_limited(
                self._max_concurrency(),
                *(self._generate_section(spec, wave_context, options.use_llm) for spec in wave2_specs),
            )
            sections.update({spec.number: payload for spec, payload in generated_wave2})

        for spec in SECTION_SPECS:
            sections.setdefault(spec.number, fallback_section(spec, "해당 실행에서 섹션을 생성하지 않음"))

        generated_at = utc_now_iso()
        company_name = financials.company_profile.get("company_name") or edgar.identity.company_name
        report_md = assemble_report(
            ticker=ticker,
            company_name=company_name,
            generated_at=generated_at,
            factpack_md=factpack.markdown,
            sections=sections,
            sources=edgar.sources,
        )

        qa_issues = None
        if options.run_qa and options.use_llm:
            qa_issues = await self._run_qa(company_name, ticker, report_md)
            report_md = assemble_report(
                ticker=ticker,
                company_name=company_name,
                generated_at=generated_at,
                factpack_md=factpack.markdown,
                sections=sections,
                sources=edgar.sources,
                qa_issues=qa_issues,
            )

        output_path.write_text(report_md, encoding="utf-8")
        if options.dump:
            self._dump_artifacts(
                artifact_dir=artifact_dir,
                edgar=edgar,
                factpack=factpack,
                summaries=summaries,
                sections=sections,
                base_context=base_context,
                qa_issues=qa_issues,
            )
        return output_path

    def _target_specs(self, section: int | None, existing_sections: dict[int, dict[str, Any]]) -> list[SectionSpec]:
        if section is None:
            return list(SECTION_SPECS)
        spec = get_section(section)
        if spec.wave == 2 and not self._has_wave1_takeaways(existing_sections):
            return [*wave_sections(1), spec]
        return [spec]

    def _has_wave1_takeaways(self, sections: dict[int, dict[str, Any]]) -> bool:
        return any(sections.get(spec.number, {}).get("key_takeaway") for spec in wave_sections(1))

    def _max_concurrency(self) -> int:
        defaults = self.config.model_config.get("defaults", {})
        try:
            return int(defaults.get("max_concurrency", 6))
        except (TypeError, ValueError):
            return 6

    async def _build_summaries(
        self,
        ticker: str,
        edgar: EdgarBundle,
        use_llm: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        tasks = []
        for filing in edgar.annual_filings:
            for item_key, item_name in [
                ("item1", "Item 1 Business"),
                ("item1a", "Item 1A Risk Factors"),
                ("item7", "Item 7 MD&A"),
            ]:
                tasks.append(self._summarize_filing_item(ticker, filing, item_key, item_name, use_llm))
        for filing in edgar.earnings_releases:
            tasks.append(self._summarize_earnings_release(ticker, filing, use_llm))
        results = await gather_limited(self._max_concurrency(), *tasks) if tasks else []
        grouped: dict[str, list[dict[str, Any]]] = {"item1": [], "item1a": [], "item7": [], "earnings": []}
        for result in results:
            grouped.setdefault(result["group"], []).append(result)
        return grouped

    async def _summarize_filing_item(
        self,
        ticker: str,
        filing: FilingRecord,
        item_key: str,
        item_name: str,
        use_llm: bool,
    ) -> dict[str, Any]:
        text = filing.items.get(item_key, "")
        group = item_key
        label = fiscal_label(filing)
        if not text:
            return {
                "group": group,
                "label": label,
                "accession_no": filing.accession_no,
                "bullets": [f"{item_name} 원문을 분리하지 못함"],
            }
        return await self._summarize_text(
            ticker=ticker,
            group=group,
            label=label,
            accession_no=filing.accession_no,
            form_type=filing.form_type,
            item_name=item_name,
            text=text,
            use_llm=use_llm,
        )

    async def _summarize_earnings_release(
        self,
        ticker: str,
        filing: FilingRecord,
        use_llm: bool,
    ) -> dict[str, Any]:
        text = filing.text_excerpt
        label = filing.report_date or filing.filing_date or filing.accession_no
        if not text:
            return {
                "group": "earnings",
                "label": label,
                "accession_no": filing.accession_no,
                "bullets": ["8-K 원문을 수집하지 못함"],
            }
        return await self._summarize_text(
            ticker=ticker,
            group="earnings",
            label=label,
            accession_no=filing.accession_no,
            form_type=filing.form_type,
            item_name="8-K Earnings Release",
            text=text,
            use_llm=use_llm,
        )

    async def _summarize_text(
        self,
        *,
        ticker: str,
        group: str,
        label: str,
        accession_no: str,
        form_type: str,
        item_name: str,
        text: str,
        use_llm: bool,
    ) -> dict[str, Any]:
        cache_path = self.config.cache_dir / "summaries" / f"{ticker}_{accession_no}_{group}_{_hash_text(text)}.json"
        if cache_path.exists():
            cached = read_json(cache_path)
            cached["group"] = group
            return cached

        bullets: list[str]
        if use_llm:
            try:
                prompt = self._prompt("map_filing.txt")
                rendered = render_template(
                    prompt,
                    {
                        "company_name": ticker,
                        "ticker": ticker,
                        "form_type": form_type,
                        "period": label,
                        "item_name": item_name,
                        "filing_text": trim_text(text, 70000),
                    },
                )
                model, temperature = self._model_options("map")
                response = await self.llm.generate_text(
                    model=model,
                    system_prompt="SEC 공시 요약을 한국어로 정확하게 작성한다.",
                    user_prompt=rendered,
                    temperature=temperature,
                )
                bullets = _lines_to_bullets(response)
            except Exception as exc:
                bullets = [f"LLM 요약 실패: {exc}", *simple_summary(text, 5)]
        else:
            bullets = simple_summary(text, 8)

        payload = {
            "group": group,
            "label": label,
            "accession_no": accession_no,
            "form_type": form_type,
            "item_name": item_name,
            "bullets": bullets,
        }
        write_json(cache_path, payload)
        return payload

    def _build_base_context(
        self,
        ticker: str,
        edgar: EdgarBundle,
        factpack: FactPack,
        summaries: dict[str, list[dict[str, Any]]],
        guidance_vs_actual: str,
    ) -> dict[str, Any]:
        company_name = edgar.identity.company_name
        segment_table = _xbrl_tables_markdown(edgar.annual_filings, ("segment", "revenue_disaggregation"))
        debt_detail = _xbrl_tables_markdown(edgar.annual_filings[:1], ("debt",))
        return {
            "ticker": ticker,
            "company_name": company_name,
            "factpack": factpack.markdown,
            "segment_table": segment_table or "N/A(연차 공시의 XBRL 렌더링에서 세그먼트 테이블을 찾지 못함)",
            "item1_summaries": _format_summary_group(summaries.get("item1", [])),
            "mdna_summaries": _format_summary_group(summaries.get("item7", [])),
            "risk_summaries": _format_summary_group(summaries.get("item1a", [])),
            "qoe_metrics": factpack.tables["qoe_metrics"],
            "peer_table": factpack.tables["peer_table"],
            "competition_excerpts": _competition_excerpts(edgar.annual_filings),
            "capital_allocation_table": factpack.tables["capital_allocation_table"],
            "debt_detail": debt_detail or "N/A(최신 연차 공시의 XBRL 렌더링에서 부채 상세 테이블을 찾지 못함)",
            "earnings_releases": _format_summary_group(summaries.get("earnings", [])),
            "guidance_vs_actual": guidance_vs_actual,
            "consensus_table": factpack.tables["consensus_table"],
            "estimate_table": factpack.tables["estimate_table"],
            "valuation_band_table": factpack.tables["valuation_band_table"],
            "technical_table": factpack.tables["technical_table"],
        }

    async def _build_guidance_table(self, ticker: str, edgar: EdgarBundle, use_llm: bool) -> str:
        """실적 보도자료(EX-99)에서 실제 실적과 발표 시점 가이던스를 구조화 추출해 시계열 표로 만든다."""
        releases = [f for f in edgar.earnings_releases if f.text_excerpt]
        if not releases or not use_llm:
            return "N/A(실적 보도자료 원문이 없거나 LLM이 비활성화되어 가이던스 추출을 생략)"
        results = await gather_limited(
            self._max_concurrency(),
            *(self._extract_earnings_facts(ticker, filing) for filing in releases),
        )
        extracted = [item for item in results if item]
        if not extracted:
            return "N/A(보도자료에서 실적·가이던스를 구조화 추출하지 못함)"
        extracted.sort(key=lambda item: item.get("filing_date", ""))
        lines = [
            "| 발표일 | 대상 분기 | 실제 매출 | 실제 EPS | 발표 시 제시된 가이던스 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for item in extracted:
            guidance_items = item.get("guidance_items") or []
            guidance = "; ".join(
                f"{g.get('metric', '')} {g.get('period', '')}: {g.get('stated', '')}".strip()
                for g in guidance_items
                if isinstance(g, dict)
            ) or "가이던스 미제시"
            lines.append(
                "| {date} | {period} | {rev} | {eps} | {guide} |".format(
                    date=item.get("filing_date", "N/A"),
                    period=item.get("period_label") or "N/A",
                    rev=item.get("revenue_actual") or "N/A",
                    eps=item.get("eps_actual") or "N/A",
                    guide=guidance.replace("|", "\\|"),
                )
            )
        lines.append("")
        lines.append("※ 각 행의 가이던스를 다음 행(다음 분기)의 실제 실적과 비교해 가이던스 신뢰도를 평가할 것.")
        return "\n".join(lines)

    async def _extract_earnings_facts(self, ticker: str, filing: FilingRecord) -> dict[str, Any] | None:
        cache_path = (
            self.config.cache_dir
            / "guidance"
            / f"{ticker}_{filing.accession_no}_{_hash_text(filing.text_excerpt)}.json"
        )
        if cache_path.exists():
            return read_json(cache_path)
        try:
            prompt = render_template(
                self._prompt("extract_earnings.txt"),
                {
                    "company_name": ticker,
                    "ticker": ticker,
                    "filing_text": trim_text(filing.text_excerpt, 40000),
                },
            )
            model, temperature = self._model_options("map")
            payload = await self.llm.generate_json(
                model=model,
                system_prompt="실적 보도자료에서 사실만 추출한다. 원문에 없는 수치를 만들지 않는다.",
                user_prompt=prompt,
                response_schema=GUIDANCE_EXTRACT_SCHEMA,
                temperature=temperature,
            )
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        payload["filing_date"] = filing.filing_date
        payload["accession_no"] = filing.accession_no
        write_json(cache_path, payload)
        return payload

    async def _generate_section(
        self,
        spec: SectionSpec,
        context: dict[str, Any],
        use_llm: bool,
    ) -> tuple[SectionSpec, dict[str, Any]]:
        if not use_llm:
            return spec, fallback_section(spec, "LLM 비활성화(--no-llm)")
        try:
            system_prompt = render_template(self._prompt("style_guide.txt"), context)
            user_prompt = render_template(self._prompt(spec.prompt_file), context)
            model, temperature = self._model_options(spec.prompt_file)
            payload = await self.llm.generate_json(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema=spec.response_schema,
                temperature=temperature,
            )
            if not isinstance(payload, dict):
                return spec, fallback_section(spec, "모델 응답이 JSON object가 아님")
            payload.setdefault("data_gaps", [])
            if spec.number != 1:
                payload.setdefault("key_takeaway", "")
            return spec, payload
        except Exception as exc:
            return spec, fallback_section(spec, str(exc))

    async def _run_qa(self, company_name: str, ticker: str, report_md: str) -> list[dict[str, Any]]:
        try:
            prompt = render_template(
                self._prompt("qa_review.txt"),
                {"company_name": company_name, "ticker": ticker, "report_md": report_md},
            )
            model, temperature = self._model_options("qa")
            response = await self.llm.generate_json(
                model=model,
                system_prompt="리서치 리포트를 수정하지 않고 문제 목록만 JSON으로 점검한다.",
                user_prompt=prompt,
                response_schema=QA_SCHEMA,
                temperature=temperature,
            )
            issues = response.get("issues", [])
            return issues if isinstance(issues, list) else []
        except Exception as exc:
            return [{"type": "QA 실패", "location": "전체", "description": str(exc)}]

    def _model_options(self, key: str) -> tuple[str, float]:
        defaults = self.config.model_config.get("defaults", {})
        sections = self.config.model_config.get("sections", {})
        override = sections.get(key, {})
        if key == "map":
            model = defaults.get("map_model", "gemini-2.5-flash-lite")
        elif key == "qa":
            model = defaults.get("qa_model", "gemini-2.5-flash")
        else:
            model = defaults.get("section_model", "gemini-2.5-flash")
        model = override.get("model", model)
        temperature = override.get("temperature", defaults.get("temperature", 0.2))
        return str(model), float(temperature)

    def _prompt(self, filename: str) -> str:
        return (self.prompts_dir / filename).read_text(encoding="utf-8")

    def _load_existing_sections(self, artifact_dir: Path) -> dict[int, dict[str, Any]]:
        sections_dir = artifact_dir / "sections"
        if not sections_dir.exists():
            return {}
        loaded = {}
        for path in sections_dir.glob("*.json"):
            try:
                number = int(path.stem.split("_", 1)[0])
                loaded[number] = read_json(path)
            except Exception:
                continue
        return loaded

    def _format_takeaways(self, sections: dict[int, dict[str, Any]]) -> str:
        rows = []
        for spec in wave_sections(1):
            payload = sections.get(spec.number, {})
            rows.append(f"{spec.number}. {spec.title_ko}: {payload.get('key_takeaway', 'N/A')}")
        return "\n".join(rows)

    def _dump_artifacts(
        self,
        *,
        artifact_dir: Path,
        edgar: EdgarBundle,
        factpack: FactPack,
        summaries: dict[str, list[dict[str, Any]]],
        sections: dict[int, dict[str, Any]],
        base_context: dict[str, Any],
        qa_issues: list[dict[str, Any]] | None,
    ) -> None:
        ensure_dir(artifact_dir)
        write_json(artifact_dir / "edgar_inputs.json", edgar.to_dict())
        write_json(artifact_dir / "summaries.json", summaries)
        write_json(artifact_dir / "prompt_context.json", base_context)
        (artifact_dir / "factpack.md").write_text(factpack.markdown, encoding="utf-8")
        sections_dir = ensure_dir(artifact_dir / "sections")
        for spec in SECTION_SPECS:
            write_json(sections_dir / f"{spec.number:02d}_{_slug(spec.title_ko)}.json", sections[spec.number])
        if qa_issues is not None:
            write_json(artifact_dir / "qa_issues.json", qa_issues)


def _format_summary_group(items: list[dict[str, Any]]) -> str:
    if not items:
        return "N/A"
    chunks = []
    for item in items:
        heading = f"### {item.get('label', 'N/A')} / {item.get('form_type', '')} / {item.get('accession_no', '')}"
        chunks.append(f"{heading}\n{bullet_list(item.get('bullets', []))}")
    return "\n\n".join(chunks)


def _xbrl_tables_markdown(filings: list[FilingRecord], categories: tuple[str, ...]) -> str:
    chunks: list[str] = []
    for filing in filings:
        tables = [filing.xbrl_tables.get(category, "") for category in categories]
        tables = [table for table in tables if table]
        if tables:
            chunks.append(f"### {fiscal_label(filing)} {filing.form_type}\n\n" + "\n\n".join(tables))
    return "\n\n".join(chunks)


def _competition_excerpts(filings: list[FilingRecord]) -> str:
    keywords = ("competition", "competitive", "customer", "concentration", "supplier", "china", "regulation", "ai")
    excerpts = []
    for filing in filings:
        item1 = filing.items.get("item1", "")
        item7 = filing.items.get("item7", "")
        text = "\n".join(part for part in (item1, item7) if part) or filing.text_excerpt
        lowered = text.lower()
        snippets = []
        for keyword in keywords:
            pos = lowered.find(keyword)
            if pos == -1:
                continue
            start = max(0, pos - 400)
            end = min(len(text), pos + 900)
            snippets.append(trim_text(text[start:end], 1500))
        if snippets:
            excerpts.append(f"### {fiscal_label(filing)} {filing.form_type}\n" + "\n\n".join(dict.fromkeys(snippets)))
    return "\n\n".join(excerpts) if excerpts else "N/A(공시 원문에서 경쟁·고객 집중 관련 발췌를 자동 식별하지 못함)"


def _lines_to_bullets(text: str) -> list[str]:
    bullets = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = line.lstrip("-*•0123456789. ").strip()
        if line:
            bullets.append(line)
    return bullets[:15] or ["요약 결과가 비어 있음"]


def _hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def _slug(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")

