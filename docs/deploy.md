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
     ADVISOR_PROVIDER_CHAIN = "gemini,groq"          # paid Gemini first; use "groq,gemini" on free keys only
     GEMINI_MIN_INTERVAL_S = "0"                      # paid Gemini: no free-tier throttling
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
- Advisor replies say *"Our assistant is briefly unavailable"* → every LLM provider failed (Gemini credit exhausted or key
  wrong, and Groq's daily quota used up). The quote is still correct (engine), only the prose is plainer. Check
  `GEMINI_API_KEY`, the Gemini billing balance, then `GROQ_API_KEY`.
- "We could not send the code" on the mobile screen → `SMS_PROVIDER` is set but not working; the grey line under it says
  why. Remove `SMS_PROVIDER` (and the `MC_*` lines) from the secrets for the on-screen demo code.

## Real SMS OTP

Without an SMS provider the app runs in demo mode: every request still gets its own random 6-digit code, shown on screen as
a labelled demo SMS. To text real codes to Indian numbers (no card, no DLT registration of your own):

1. Sign up at **https://console.messagecentral.com/signup** (Message Central VerifyNow) with an email and a password.
2. On the console home page copy your **customer id** (`C-XXXXXXXX`) and note the free test credit balance.
3. Add to `.env` (local) and to the app's **Secrets** (Streamlit Cloud):
   ```toml
   SMS_PROVIDER = "messagecentral"
   MC_CUSTOMER_ID = "C-XXXXXXXX"
   MC_EMAIL = "you@example.com"
   MC_PASSWORD = "your-console-password"
   ```
4. Restart / save secrets. `GET /health` should show `"otp_mode": "sms:messagecentral"`.
5. **Day-1 test:** request a code for your own number **and** a friend's number on a different network. Both should
   arrive (sender `UTOMOB`, text ending "Powered by U2opia"), and the console balance should drop. If the friend's
   number does not receive it, the trial is limited to your own number: switch to the backup below.

Notes: Message Central codes are valid for 60 seconds by default (configurable 20–300 s in their console), and the app
shows that timer. Our own limits still apply in front of the provider: 30-second resend cooldown, 5 codes per number per
hour, 5 tries per code. After the free credits it costs about ₹0.30 per delivered SMS.

**Backup: 2Factor.in.** Sign up at 2factor.in (email + phone; free test credits), copy the API key, then set
`SMS_PROVIDER = "2factor"` and `TWOFACTOR_API_KEY = "..."`. It uses their default OTP template.

Providers ruled out for a no-card demo: Twilio, Vonage, Plivo, Infobip and Sinch trials can only text pre-verified
numbers, so a judge's own phone would not receive the code.

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
- The demo conversations are already recorded in the reply cache (committed). To re-record them (`backend/`: `python scripts/record_demo.py`,
  then `git add -f` the files it prints and push), so the advisor answers even if the API is dead on the day.
- Keep `docs/demo-transcripts.md` open as the fallback script.
