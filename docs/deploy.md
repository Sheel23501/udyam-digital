# Deploying Udyam Digital (free, no card)

The recommended setup is **one Streamlit Community Cloud app**: the UI imports the backend package and serves the API in the
same process (`API_MODE = "inprocess"`). Nothing else to host, nothing to pay for.

## A. Streamlit Community Cloud, one process (10 minutes)

1. Go to **https://share.streamlit.io** and sign in **with GitHub** (the account that owns `Sheel23501/udyam-digital`).
2. Click **Create app** (top right) → **Deploy a public app from GitHub** (works for private repos too once the Streamlit
   GitHub app has access; grant it when asked).
3. Fill the form:
   - **Repository:** `Sheel23501/udyam-digital`
   - **Branch:** `main`
   - **Main file path:** `frontend/app.py`
   - **App URL:** choose a name, e.g. `udyam-digital` → the app becomes `https://udyam-digital.streamlit.app`
4. Click **Advanced settings**:
   - **Python version:** `3.13` (if not offered, `3.12` also works)
   - **Secrets:** paste the block below (your real keys from `.env`; never commit this block)
     ```toml
     API_MODE = "inprocess"
     TODAY = "2026-07-15"
     STAFF_PIN = "<choose a private PIN>"
     GEMINI_VISION_MODEL = "gemini-3.5-flash-lite"
     GEMINI_MODEL = "gemini-3.5-flash-lite"
     ADVISOR_MODEL_GROQ = "openai/gpt-oss-120b"
     ADVISOR_PROVIDER_CHAIN = "groq,cerebras,mistral,openrouter,gemini"
     GROQ_API_KEY = "gsk_..."
     GEMINI_API_KEY = "AIza..."
     ```
5. Click **Deploy**. The first build takes 3–6 minutes (it installs the root `requirements.txt` and `packages.txt`).
   Watch the log on the right; "You can now view your Streamlit app" means it is up.
6. **Smoke test on your phone** (open the URL in the phone browser):
   language → your mobile number → the 6-digit code shown in the demo SMS (or texted, if an SMS provider is set) → tap the first example chip → card → **See my price** → toggles →
   **Continue** → tick the 4 required purposes → **I agree** → **Use a sample applicant** → `K11` → **Verify** (must say
   *Could not verify*, old bill) → **Try another sample** → `K03` → **Verify** (*Verified*) → **Place my order** → tracker →
   **Advance stage** → **Finish**. Then open the sidebar (top-left arrow) → **backoffice** → your `STAFF_PIN`.
7. Later changes: every push to `main` redeploys automatically. Secrets can be edited any time from the app's menu
   (**⋮ → Settings → Secrets**); the app restarts on save.

### If the build fails
- *"No matching distribution"* for a package → set Python 3.12 in Advanced settings and reboot.
- *ImportError: libGL / libglib* → `packages.txt` must contain `libglib2.0-0` (it does); reboot the app.
- App shows *"The service is starting up"* → `API_MODE` secret is missing or misspelled; must be exactly `inprocess`.
- Advisor replies say *"Our assistant is briefly unavailable"* → Groq quota is exhausted or the key is wrong; the quote
  is still correct (engine), only the prose is plainer. Check `GROQ_API_KEY`.

## B. Two services (API on Render, UI on Streamlit Cloud)

Use this only if you want the HTTP API itself public for judges (e.g. to share `/docs`).

1. **Render:** https://dashboard.render.com → **New → Blueprint** → connect `Sheel23501/udyam-digital` → it reads
   `render.yaml` → set `GROQ_API_KEY` and `GEMINI_API_KEY` when prompted → **Apply**. Free plan; first build ~5 minutes.
   The API URL is shown on the service page (`https://udyam-digital-api.onrender.com`); check `/health` and `/docs`.
   Free services sleep after 15 idle minutes and take ~40 s to wake: open `/health` before a demo.
2. **Streamlit Cloud:** as in A, but secrets are only
   ```toml
   API_MODE = "http"
   BACKEND_URL = "https://udyam-digital-api.onrender.com"
   STAFF_PIN = "<choose a private PIN>"
   ```

## C. Docker (any VM, judges)

```bash
git clone https://github.com/Sheel23501/udyam-digital.git && cd udyam-digital
cp .env.example .env            # add keys (optional: engine, KYC samples and offline advisor work without any)
docker compose up --build       # API http://localhost:8000 (docs at /docs), UI http://localhost:8501
```

## Before the demo (any option)

- Open the app once 10 minutes before, so it is warm.
- Run the demo conversations into the reply cache when Groq quota is available (`backend/`: `python scripts/record_demo.py`,
  then `git add -f` the files it prints and push), so the advisor answers even if the API is dead on the day.
- Keep `docs/demo-transcripts.md` open as the fallback script.
