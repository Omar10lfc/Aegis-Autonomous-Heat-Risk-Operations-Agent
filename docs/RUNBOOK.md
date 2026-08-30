# Aegis Runbook — how to run it, and how to prove it works

This is the step-by-step operating guide. For architecture see `docs/architecture.md`.

---

## 1. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.12+ | `python --version` |
| Node.js | 18+ (20/22 recommended) | `node --version` |
| Docker Desktop (optional) | any recent | `docker --version` |

## 2. One-time setup

From the repo root (`aegis/`):

```powershell
# Backend
python -m venv .venv
.venv\Scripts\activate            # Windows PowerShell
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

## 3. Environment variables

Copy `.env.example` → `.env` in the repo root and fill in:

| Variable | Required? | Purpose |
|---|---|---|
| `FORTYGUARD_API_KEY` | for live mode only | FortyGuard key. Header used is `api-key:` (not Bearer). |
| `FORTYGUARD_LIVE` | no | **`false` by default** — runs on cached payloads, zero credit spend. Set `true` only when you authorize real API calls. |
| `FORTYGUARD_MAX_AOI_MI2` | no | AOI cap enforced pre-submit. Default 10 mi² until plan confirmed Premium. |
| `OPENROUTER_API_KEY` | optional | Enables the LLM planner/synthesizer. Without it the agent falls back to a deterministic heuristic planner — everything still works. |
| `OPENROUTER_MODEL` | no | Must end with `:free` (enforced). Default `openai/gpt-oss-20b:free`. |
| `LANGCHAIN_API_KEY` | optional | LangSmith tracing. Without it, tracing env vars are set but nothing uploads; the pipeline still runs. |

For the frontend, create `frontend/.env.local`:

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

Never commit `.env` or `.env.local`. Keys are redacted from LangSmith traces via `app/tools/redact.py`.

## 4. Running locally (two terminals)

**Terminal 1 — backend (from repo root):**

```powershell
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Wait for: `Application startup complete.`

**Terminal 2 — frontend:**

```powershell
cd frontend
npm run dev
```

Open http://localhost:3000.

### Docker alternative (backend only)

```bash
docker compose up --build backend
```

## 5. How to know it did its purpose (verification)

The agent's purpose: **plain-English brief in → ranked, source-cited heat-risk memo out, with an auditable trace.** Verify each link of that chain:

### 5a. Health check

```
GET http://localhost:8000/health
→ {"status":"ok","fortyguard_mode":"cached","llm_model":"openai/gpt-oss-20b:free"}
```

### 5b. End-to-end run through the UI

1. Open http://localhost:3000, click **Use example brief**, then **Run agent**.
2. The status bar should advance through stages: `queued → planner → executor → analyzer → synthesizer`.
3. Within ~30–60 s you get:
   - A markdown memo with a **Ranked sites** section (sorted hottest first),
   - A **Recommendation**, and
   - A **Citations** list where every claim carries `{endpoint, activity_id, value}`.
4. A **LangSmith trace ↗** link appears next to the status and at the bottom of the report. Clicking it must open a trace showing all four nodes (planner → executor → analyzer → synthesizer) with per-node inputs/outputs and latency. **That link working is the "auditable reasoning" judging criterion — check it before every demo.**

### 5c. Same run via raw HTTP (no browser)

```powershell
$job = Invoke-RestMethod -Uri http://localhost:8000/brief -Method Post -ContentType "application/json" `
  -Body '{"brief":"Which Phoenix routes crossed dangerous heat thresholds last month?"}'
Start-Sleep 30
Invoke-RestMethod -Uri "http://localhost:8000/status/$($job.job_id)"
(Invoke-RestMethod -Uri "http://localhost:8000/report/$($job.job_id)").markdown
```

Pass criteria:
- `status` becomes `succeeded`
- report contains ≥1 citation whose `activity_id` is non-null
- ranked sites are ordered by descending max value
- if the planner fell back, the memo says `heuristic-fallback` under **Planner model**

### 5d. Guardrail checks (the two hard constraints)

Submit these to `POST /brief`; each must produce a **failed job with a clear validation error**, not a live API call:

- Non-U.S. coordinates (e.g. a London warehouse) → rejected: outside U.S.
- A date before `2021-01-01` → rejected.
- An absurdly large AOI (>10 mi² default) → rejected.

These validators exist so out-of-bounds requests never burn credits.

### 5e. Test suite

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected: **all pass**, including 12 eval cases in `test_agent_eval.py` covering snapshot / exceedance / persistence across logistics, insurance, and real-estate framings. These also run in CI (`.github/workflows/pytest.yml`) on every push.

## 6. Going live with real FortyGuard data (credit spend!)

Only do this when ready to burn credits:

1. In `.env`: `FORTYGUARD_LIVE=true` (key already present).
2. Restart the backend; `/health` now reports `"fortyguard_mode": "live"`.
3. Submit ONE small brief first (single site, one hour, granularity 100) and watch `GET /status/{job_id}` until `succeeded`. Verify the `activity_id`s in citations are real (not `cached-*`).
4. Live calls poll with backoff 3 s → 6 s → 12 s… capped at 30 s, hard timeout 180 s. Failed tasks cost no credits; rejected-by-validator tasks never leave this machine.

Known live-mode caveat: the first submit attempt uses the vendored official `fortyguard` client; if its import fails, it falls back to direct HTTP against the documented All-plans endpoints.

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Memo says `Planner model: heuristic-fallback` | The free OpenRouter model returned invalid JSON or was rate-limited; the deterministic planner took over. Output is still correct. Try again or change `OPENROUTER_MODEL`. |
| First run takes ~30–60 s even in cached mode | The planner attempts up to 3 free LLM models with backoff before falling back. Cached executor responses themselves are instant. |
| Frontend shows `TypeError: fetch failed` | Backend not running, or `NEXT_PUBLIC_BACKEND_URL` wrong. After changing it, restart `npm run dev` (it's baked in at build/dev start). |
| `ModuleNotFoundError: langgraph` | You're using system Python instead of `.venv\Scripts\python.exe`. |
| Job stuck in `running` forever >3 min | Poll timeout is 180 s; after that the call record fails with a clear error. If genuinely hung, restart uvicorn. |
| 409 from `GET /report/{id}` | Report only exists once status is `succeeded`. Poll `/status/{id}` first. |

## 8. Deploying (Render backend + Vercel frontend)

Repo layout is already deploy-ready: `render.yaml` (backend blueprint), `backend/Dockerfile`, and `frontend/vercel.json`.

### 8a. One-time repo push

```powershell
git init
git add -A
git commit -m "Aegis: goal-driven heat-risk agent"
```

Push to a GitHub repo (e.g. `FortyGuard-Tech/aegis`). `.gitignore` already excludes `.env`, keys, and build artifacts.

### 8b. Backend on Render

1. Render dashboard → **New → Blueprint** → connect the GitHub repo.
2. It reads `render.yaml` and provisions the `aegis-backend` service (Docker, `python:3.12-slim`).
3. In the service's **Environment** tab, set these secrets (marked `sync: false` in the blueprint):
   - `FORTYGUARD_API_KEY` (only if you enable live mode)
   - `GROQ_API_KEY` and/or `OPENROUTER_API_KEY`
   - `LANGCHAIN_API_KEY` (optional)
4. After deploy, the service shows a URL like `https://aegis-backend.onrender.com`. Verify: open `{url}/health` → `{"status":"ok",...}`.
5. To use real FortyGuard data, add `FORTYGUARD_LIVE=true` and restart.

### 8c. Frontend on Vercel

1. Vercel → **Add New → Project** → import the same GitHub repo.
2. Root directory: `frontend`. Framework preset: Next.js.
3. Add env var `NEXT_PUBLIC_BACKEND_URL=https://aegis-backend.onrender.com` (needed even in cached mode so polling works).
4. Deploy. Site URL like `https://aegis-frontend.vercel.app`. Open it, run the example brief, confirm the status bar advances and a cited memo + map render.

### 8d. Unified All-in-One Deployment on Hugging Face Spaces (Docker SDK)

Aegis includes a multi-stage `Dockerfile` that packages both the Next.js frontend and FastAPI backend into a single container running on Hugging Face Spaces:

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Set Space Name (e.g. `aegis-heat-risk-agent`).
3. Select **Docker** as the Space SDK (Blank).
4. Connect or push your repo:
   ```powershell
   git remote add space https://huggingface.co/spaces/<your-username>/<space-name>
   git push space main
   ```
5. In **Space Settings → Variables and Secrets**, add your environment variables:
   - `GROQ_API_KEY` (or `OPENAI_API_KEY`)
   - `FORTYGUARD_API_KEY` (optional)
   - `FORTYGUARD_LIVE` = `false`
   - `LANGCHAIN_API_KEY` (optional)
6. Hugging Face Spaces will automatically build the container, serve port `7860`, and launch the full interactive app!

Caveats:
- Jobs live in-process, so a Render instance restart clears in-flight `job_id`s; re-submit to restart a run. Fine for a demo.
- The free Render plan powers down idle instances; the first request after idle takes ~30–60 s to cold start.

## 9. What "done" looks like (deliverable status)

| Deliverable | Status |
|---|---|
| Planner → Executor → Analyzer → Synthesizer (LangGraph + LangSmith per node) | ✅ done |
| FastAPI `POST /brief`, `GET /status/{id}`, `GET /report/{id}`, `GET /health` | ✅ done |
| Next.js frontend (brief → live status → cited report + trace link) | ✅ done |
| Eval harness, 12 mocked cases | ✅ done, green |
| Retry/backoff/timeout + U.S./date/AOI pre-submit validation | ✅ done |
| Secrets redaction from traces (`tools/redact.py`) | ✅ done |
| Live FortyGuard calls behind explicit opt-in flag | ✅ implemented, off by default |
| Deploy backend (Render) + frontend (Vercel) | ⬜ pending — see §8 |
| Demo video ≤3 min (`docs/demo_script.md` drafted) | ⬜ script drafted, video pending |
