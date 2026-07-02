# Deep Research

Standalone CLI and API pipeline for Korean institutional-style U.S. equity research reports.

## Setup

```bash
cd deep_research
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `GEMINI_API_KEY` and a real `EDGAR_USER_AGENT` contact string before live SEC/Gemini runs.

For API mode, also set:

```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
DEBUG=true
```

Run `migrations/002_research.sql` in the same Supabase project that contains the existing `tickers` table.

## CLI Usage

```bash
python scripts/generate_report.py AAPL -o reports/AAPL.md
```

Useful development options:

```bash
python scripts/generate_report.py AAPL --section 3 -o reports/AAPL.md
python scripts/generate_report.py AAPL --no-llm -o reports/AAPL_structure.md
python scripts/generate_report.py AAPL --qa -o reports/AAPL.md
```

The CLI writes intermediate artifacts next to the output file in `{stem}_artifacts/`, including the factpack, prompt context, SEC inputs, filing summaries, and section JSON.

## API Usage

```bash
uvicorn app.main:app --reload --port 8001
```

Endpoints:

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/v1/research/{symbol}` | Start a job, return cached report if a fresh one exists |
| `GET` | `/v1/research/{symbol}` | Read the latest completed report |
| `GET` | `/v1/research/jobs/{job_id}` | Poll job status and completed report |
| `GET` | `/health` | Health check |

Example:

```bash
curl -X POST http://localhost:8001/v1/research/AAPL
curl http://localhost:8001/v1/research/jobs/1
```

Cloud Run can use the included `Dockerfile`; keep CPU always allocated for long-running background jobs.
