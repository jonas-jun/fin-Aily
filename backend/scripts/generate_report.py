#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.pipeline.generate import GenerateOptions, ResearchPipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a deep research report for a U.S. listed ticker.")
    parser.add_argument("ticker", help="Ticker symbol, e.g. AAPL")
    parser.add_argument("-o", "--output", type=Path, help="Output Markdown path")
    parser.add_argument("--section", type=int, choices=range(1, 11), help="Regenerate one section only")
    parser.add_argument("--no-dump", action="store_true", help="Do not write intermediate artifacts")
    parser.add_argument("--no-llm", action="store_true", help="Skip Gemini calls and create a structural report")
    parser.add_argument("--qa", action="store_true", help="Run optional QA pass after assembly")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    pipeline = ResearchPipeline()
    output = await pipeline.run(
        GenerateOptions(
            ticker=args.ticker,
            output_path=args.output,
            section=args.section,
            dump=not args.no_dump,
            use_llm=not args.no_llm,
            run_qa=args.qa,
        )
    )
    print(f"Report written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

