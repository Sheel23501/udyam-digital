# Udyam Digital — Accel Business SMB onboarding (YTL Hackathon 2026, Track A)

A phone-first, Hindi/English journey that lets a small business owner discover the right Accel Business bundle, get a single-price quote, complete Smart KYC against mock GSTIN/Udyam registries, and track activation — with no salesperson in the loop.

**Stack:** Python 3.13 · FastAPI · SQLite · Streamlit · advisor LLM on Groq `openai/gpt-oss-120b` (OpenAI-compatible, fallback Cerebras → Gemini) · KYC vision on Gemini (`google-genai`). Runs entirely on free tiers.

**Design rule:** the rules engine (`backend/app/engine/`) decides what may be sold; the LLM only asks questions and narrates the engine's result. Every bundle is re-validated before it is shown.

## Run locally

```bash
cp .env.example .env            # add GROQ_API_KEY (advisor) and GEMINI_API_KEY (KYC vision); CEREBRAS_API_KEY optional
/opt/homebrew/bin/python3.13 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt
./run_local.sh                  # backend :8000, UI :8501
```

Free keys: Groq at console.groq.com, Cerebras at cloud.cerebras.ai, Gemini at aistudio.google.com/apikey. No card needed for any of them.

## The app (Streamlit, phone-shaped)

`./run_local.sh` starts the API on :8000 and the UI on :8501. Or run only `streamlit run frontend/app.py`: when no backend
answers, the UI imports the backend package and calls it in-process (`API_MODE=auto`), so one process is enough.

Journey: language → mobile + OTP (demo code `1234`) → advisor chat (Hindi / English / Hinglish, example chips) → recommendation card
drawn from engine JSON → quote with toggles and quantities, every change re-validated → DPDP consent with itemised purposes → Smart KYC
(upload four photos, or pick sample applicant K01–K12) → order → tracker with dated stages, demo "advance" and consent withdrawal.
Back-office page (sidebar, staff PIN `1234`): scored queue of unclosed leads, lead detail with reasons, audit log, retention purge, erasure.

Headless UI tests drive the whole journey with Streamlit's `AppTest` and no server: `pytest frontend/tests -q` from the repo root.

## Deploy (all free, no card)

**Option A — one process on Streamlit Community Cloud (recommended):** New app → this repo → main file `frontend/app.py` →
Advanced settings: Python 3.13, secrets:

```toml
API_MODE = "inprocess"          # the UI serves the API in the same process
GROQ_API_KEY = "..."
GEMINI_API_KEY = "..."
TODAY = "2026-07-15"
STAFF_PIN = "1234"
```

The root `requirements.txt` and `packages.txt` are for this deployment. No other service is needed.

**Option B — two services:** API on Render via `render.yaml` (Blueprint, Docker, root `backend/`, set the two keys when asked),
UI on Streamlit Community Cloud with secrets `API_MODE = "http"` and `BACKEND_URL = "https://<your-render-url>"`.

**Docker (judges / any VM):** `cp .env.example .env`, add keys (optional), then `docker compose up --build` → API :8000, UI :8501.
Docker is not installed on the development Mac, so the images were written to the compose spec but not built here.

## For judges

All commands run from `backend/` with the virtualenv active.

- **Advisor scenarios as profiles** (rules engine only, instant): `python scripts/run_scenarios.py path/to/folder/` — 30 shipped in `tests/scenarios/`.
- **Advisor scenarios as transcripts** (live LLM + engine): `python scripts/run_llm_scenarios.py path/to/folder/` — 16 shipped in `tests/llm_scenarios/`. Each turn is typed to the advisor; the check is on the engine result and on `validate()` (zero rule violations), never on the prose. Add `--runs 3` to check flakiness, `--save docs/demo-transcripts.md` to write transcripts.
- **KYC report** on the 12 sample applicants: `python scripts/kyc_report.py --key tests/kyc_answer_key_images.json` (cached extractions ship in `data/cache/extractions/`, so this needs no API key).
- **Tests:** `pytest -q` — rules, dependency closure, a 900-profile invariant grid, KYC validators, image gates, and the advisor tool loop with a fake provider (no network).

Scenario JSON formats are documented at the top of each script.

## Advisor on free tiers

Groq's free tier allows 8,000 tokens a minute and **200,000 tokens a day** on `gpt-oss-120b`. One conversation is 5–8 model calls of ~2k tokens (about 10–18k tokens), so a single key covers roughly 15 conversations a day; the provider chain (`ADVISOR_PROVIDER_CHAIN`) moves to Cerebras, Mistral, OpenRouter or Gemini when Groq is busy, skipping any provider without a key.

**Three layers keep the recommendation correct whatever the LLM does:**
1. The model never picks products. It records facts with `update_profile`; the rules engine returns the bundle, and the model only narrates it. Explicit product asks in the owner's words ("1 Gbps fibre", "toll-free") are recorded by the server even if the model forgets.
2. Once the five facts are known and the owner has said what they want solved, the server runs the quote itself if the model keeps asking questions.
3. If every provider is down, `app/advisor/chat.py` reads the facts from the owner's words with rules (`language.read_facts`), asks the next question, and explains the engine result in Hindi or English. All 16 transcript scenarios pass in this mode (`ADVISOR_OFFLINE=1 python scripts/run_llm_scenarios.py --allow-offline`, also a pytest). The cached reply for an exact transcript (`data/cache/advisor/`) is used first when present.

Live transcripts recorded on Groq are in `docs/demo-transcripts.md`.

## API (what the UI calls, open to judges)

Start it with `cd backend && uvicorn app.main:app --reload --port 8000`; interactive docs at `http://localhost:8000/docs`.

| Step | Call | Notes |
|---|---|---|
| Start | `POST /sessions {language, partner_code?}` | returns `session_id` |
| Advisor | `POST /advisor/chat {session_id, text}` | reply + `profile` + `recommendation` (engine JSON the card is drawn from) |
| Quote edits | `POST /engine/validate {profile, items}` | violations with reasons, price, what else is addable |
| Engine only | `POST /engine/recommend` (Profile) · `GET /catalogue` | deterministic, no LLM |
| Consent | `GET /consent/notice?lang=hi` · `POST /consent {session_id, purposes, language}` · `DELETE /consent/{id}` | all four required purposes must be ticked |
| KYC | `POST /kyc/upload` (multipart: `session_id`, `doc_type`, `file`) · `POST /kyc/run {session_id, sample_applicant?}` · `GET /kyc/{application_id}` | **403 without consent.** `sample_applicant: "K01".."K12"` uses the provided packs from cached extractions |
| Registry | `GET /lookup/gstin/{gstin}` · `GET /lookup/udyam/{number}` | masked output, 30 req/min, audited |
| Order | `POST /orders {session_id, items?}` · `GET /orders/{id}` · `POST /orders/{id}/advance` | needs a PASS KYC on the session; ETA per stage |
| Back-office | `GET /backoffice/leads` · `GET /backoffice/leads/{id}/score` · `POST /backoffice/handoff` · `GET /backoffice/audit` | live unclosed sessions + 200 scored historical drops |
| Privacy admin | `POST /admin/retention/run` · `POST /admin/erase/{session_id}` | retention purge; DPDP erasure request |

Privacy plumbing lives in `backend/app/privacy/`: `consent.py` (itemised purposes, withdrawal), `masking.py`, `audit.py` (masked subjects only), `retention.py` (30 days rejected / 90 days verified, erasure).

_Sections below are filled in as the build progresses: architecture, what is mocked vs real, privacy note, known limitations._
