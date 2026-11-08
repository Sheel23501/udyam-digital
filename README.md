# Udyam Digital — Accel Business SMB onboarding (YTL Hackathon 2026, Track A)

A phone-first, Hindi/English journey that lets a small business owner discover the right Accel Business bundle, get a single-price quote, complete Smart KYC against mock GSTIN/Udyam registries, and track activation — with no salesperson in the loop.

**Stack:** Python 3.13 · FastAPI · SQLite · Streamlit · Gemini (`google-genai`)

## Run locally

```bash
cp .env.example .env            # add your GEMINI_API_KEY
/opt/homebrew/bin/python3.13 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r frontend/requirements.txt
./run_local.sh                  # backend :8000, UI :8501
```

## For judges

- Run your own advisor scenarios: `cd backend && python scripts/run_scenarios.py path/to/scenarios/`
- Run the KYC report on the 12 sample applicants: `cd backend && python scripts/kyc_report.py data/kyc_documents`
- Tests: `cd backend && pytest -q`

_Sections below are filled in as the build progresses: architecture, what is mocked vs real, privacy note, known limitations._
