# How to check that Udyam Digital works

This walks you from a fresh clone to a verified API in about 20 minutes. Every expected result below was produced by
running these exact commands. **No API keys are needed** for any step except the optional live-LLM step 8.

- Steps 1–3 set up the code.
- Step 4 runs every automated check in one go. If that is all green you can stop there.
- Steps 5–7 start the API and check each endpoint by hand, so you see what it actually does.
- Steps 8–11 are optional: live LLM, Docker, your own test scenarios, the UI.

Commands are for macOS/Linux (bash/zsh). On Windows use **WSL** or **Git Bash**, or do step 6 in the browser page at
`http://localhost:8000/docs` (every endpoint has a "Try it out" button, no curl needed).

---

## 1. What you need

| Item | Version / note |
|---|---|
| Python | **3.13** (what CI and development use). Check with `python3 --version` |
| git | any |
| Disk | about 1.5 GB for the virtual environment |
| Free ports | 8000 (API), 8501 (UI, only for step 11) |
| API keys | none for the core checks; optional for step 8 |

## 2. Get the code

```bash
git clone https://github.com/Sheel23501/udyam-digital.git
cd udyam-digital
```

Everything below runs from this `udyam-digital` folder unless a step says `cd backend`.

## 3. Install

```bash
python3.13 -m venv .venv          # or: python3 -m venv .venv  if python3 is already 3.13
source .venv/bin/activate         # Windows Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt pytest
```

This takes 2–5 minutes. The last line should say `Successfully installed ...`.

No `.env` file is needed. The database is built automatically from the CSVs in `backend/data/` the first time the code runs.

## 4. One-shot check: run everything automatically (≈ 1 minute)

```bash
cd backend
pytest -q                                                        # 1) all backend tests
cd .. && pytest frontend/tests -q && cd backend                   # 2) the whole UI journey, headless
python scripts/run_scenarios.py | tail -1                         # 3) 30 advisor scenarios through the rules engine
python scripts/kyc_report.py --key tests/kyc_answer_key_images.json   # 4) Smart KYC on the 12 sample applicants
ADVISOR_OFFLINE=1 python scripts/run_llm_scenarios.py --allow-offline | tail -1   # 5) 16 chat conversations, no LLM
cd ..
```

Expected:

| Check | Expected last line |
|---|---|
| 1) backend tests | about `2050 passed` (no skips; the count grows as tests are added) |
| 2) UI tests | about `11 passed` |
| 3) scenarios | `30/30 passed` |
| 4) KYC | a 12-row table, then `12/12 match the answer key` |
| 5) conversations | `16/16 passed · 0 LLM calls · 0 tokens ...` |

The KYC table (check 4) must show these verdicts — this is the answer key for the 12 sample applicants:

| Applicant | Verdict | Why |
|---|---|---|
| K01 | FAIL | GSTIN cancelled in the registry; Udyam number missing |
| K02 | REVIEW | GST certificate photo is rotated (re-take, not a rejection) |
| K03 | PASS | everything matches |
| K04 | REVIEW | GST certificate photo is blurred |
| K05 | FAIL | Udyam certificate missing |
| K06 | FAIL | GSTIN check digit fails; registry has a different number (tampered digit) |
| K07 | FAIL | legal name on GST certificate does not match Udyam |
| K08 | PASS | everything matches |
| K09 | PASS | everything matches |
| K10 | FAIL | signatory is not the business's person of record |
| K11 | FAIL | electricity bill is 257 days old (must be ≤ 90) |
| K12 | PASS | everything matches |

## 5. Start the API

Open a **second terminal**, go to the repo folder, then:

```bash
source .venv/bin/activate
cd backend
ADVISOR_OFFLINE=1 STAFF_PIN=check-1234 uvicorn app.main:app --port 8000
```

Wait for `Uvicorn running on http://127.0.0.1:8000`. Leave this terminal open.

`ADVISOR_OFFLINE=1` makes the chat advisor answer with its built-in rules instead of calling an LLM, so the checks
below are deterministic and need no key. Step 8 shows the live LLM.

Open **http://localhost:8000/docs** in a browser: it lists every endpoint with its request and response format.

## 6. Check every endpoint by hand

Go back to the **first terminal** (repo folder, venv active). Run the blocks **in order**: later blocks reuse the
`SID` (session id) and other values that earlier blocks save. `python3 -m json.tool` just pretty-prints JSON.

<!-- check:start -->
**6.1 Health** — the API is up and has loaded the data.

```bash
curl -s localhost:8000/health | python3 -m json.tool
```
Expect `"ok": true`, `"catalogue_products": 25`, `"gstin_registry_rows": 3534`, `"udyam_registry_rows": 2723`,
`"leads_rows": 5000`. `advisor_providers` lists LLM providers that have a key (empty without a `.env`; that is fine).

**6.2 Catalogue** — 25 products with their eligibility rules.

```bash
curl -s localhost:8000/catalogue | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d), 'products'); print([(p['id'], p['name']) for p in d[:3]])"
```
Expect `25 products` and the first three: Biz Fibre 100, Biz Fibre 300, Biz Fibre 1G.

**6.3 Rules engine: recommend** — a kirana shop with no GST that wants WhatsApp ordering.

```bash
curl -s -X POST localhost:8000/engine/recommend -H 'content-type: application/json' \
  -d '{"business_type":"Kirana store","employee_count":2,"num_sites":1,"city":"Lucknow","has_gstin":false,"needs":["whatsapp_customers"]}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('items:', [(i['product_id'], i['qty']) for i in d['items']]); print('excluded:', [(e['product_id'], e['reason']) for e in d['excluded']]); print('from Rs', d['monthly_min'], '/month')"
```
Expect `items: [('P04', 1), ('P07', 1), ('P18', 1)]`, `excluded: [('P15', 'GSTIN_REQUIRED')]`, `from Rs 1497 /month`.
WhatsApp Business API (P15) needs GST, so the engine leaves it out and offers a website (P18) instead.

**6.4 Rules engine: validate** — a 6-person tailor tries to add Managed Firewall (needs 10 staff) and a product that does not exist.

```bash
curl -s -X POST localhost:8000/engine/validate -H 'content-type: application/json' \
  -d '{"profile":{"business_type":"Tailoring shop","employee_count":6,"num_sites":1,"city":"Delhi","has_gstin":true},"items":{"P04":1,"P21":1,"P99":1}}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('violations:', [(v['product_id'], v['reason']) for v in d['violations']])"
```
Expect `violations: [('P99', 'UNKNOWN_PRODUCT'), ('P21', 'MIN_EMPLOYEES')]`.

**6.5a Mobile verification (OTP)** — a fresh random code per request; wrong codes count down; the right code gives a
single-use token that creates a phone-verified session. With no SMS provider configured (the default) the API returns
the code as `demo_code` so it can be shown on screen; with a real provider it is only texted.

```bash
PHONE=9$(python3 -c "import random; print(random.randint(100000000, 999999999))")
OTP=$(curl -s -X POST localhost:8000/auth/otp/request -H 'content-type: application/json' -d "{\"phone\":\"+91 $PHONE\"}")
echo "$OTP" | python3 -c "import sys,json; d=json.load(sys.stdin); print('sent to', d['phone_masked'], '| provider', d['provider'], '| expires in', d['expires_in'], 's | code', d['demo_code'])"
RID=$(echo "$OTP" | python3 -c "import sys,json; print(json.load(sys.stdin)['request_id'])")
CODE=$(echo "$OTP" | python3 -c "import sys,json; print(json.load(sys.stdin)['demo_code'])")
curl -s -X POST localhost:8000/auth/otp/verify -H 'content-type: application/json' -d "{\"request_id\":\"$RID\",\"code\":\"000000\"}" | python3 -m json.tool
TOKEN=$(curl -s -X POST localhost:8000/auth/otp/verify -H 'content-type: application/json' -d "{\"request_id\":\"$RID\",\"code\":\"$CODE\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['otp_token'])")
curl -s -X POST localhost:8000/sessions -H 'content-type: application/json' -d "{\"language\":\"en\",\"otp_token\":\"$TOKEN\"}" | python3 -m json.tool
curl -s -o /dev/null -w "same token again -> %{http_code}\n" -X POST localhost:8000/sessions -H 'content-type: application/json' -d "{\"otp_token\":\"$TOKEN\"}"
curl -s -o /dev/null -w "new code right away -> %{http_code}\n" -X POST localhost:8000/auth/otp/request -H 'content-type: application/json' -d "{\"phone\":\"$PHONE\"}"
```
Expect `sent to XXXXXX....  | provider demo | expires in 300 s | code <6 random digits>` (a different code every time);
then `"error": "wrong_code"` with `"attempts_left": 4`; then a session with `"phone_verified": true` and the masked
number; then `same token again -> 401` (single use) and `new code right away -> 429` (30-second resend cooldown).
After 5 wrong tries a code is locked; codes expire after 5 minutes; a number gets at most 5 codes an hour.

**6.5 Start a customer session** — saves the id in `SID` for the next blocks. (The API also accepts sessions without
an OTP token so it is easy to test; start the server with `REQUIRE_OTP=1` to make verification mandatory.)

```bash
SID=$(curl -s -X POST localhost:8000/sessions -H 'content-type: application/json' -d '{"language":"en"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
echo "session: $SID"
```
Expect a 12-character id, e.g. `session: 3f9c2a7d1b04`.

**6.6 Advisor chat** — the owner describes the business in one message.

```bash
curl -s -X POST localhost:8000/advisor/chat -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"text\":\"Pharmacy in Pune, 3 staff, one shop, GST registered, I want CCTV cameras\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('provider:', d['provider']); print('bundle:', [(b['id'], b['qty']) for b in d['recommendation']['bundle']]); print(d['text'][:300])"
```
Expect:
```
provider: offline
bundle: [('P01', 1), ('P07', 2), ('P23', 2)]
(Our assistant is briefly unavailable, so here is the quote straight from our rules engine.)
Here is what I suggest for your business: ...
```
Two cloud cameras (P23) pull in a fibre line (P01) because cameras need one; two business SIMs (P07) for the staff.
The "briefly unavailable" sentence is how the advisor labels a rules-only reply; with `ADVISOR_OFFLINE=1` that is
expected. The bundle and price are computed by the rules engine in both modes, never by the language model.

**6.7 Consent notice** — what the owner must agree to, in Hindi.

```bash
curl -s "localhost:8000/consent/notice?lang=hi" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['version']); [print(p['id'], '(required)' if p['required'] else '(optional)') for p in d['purposes']]"
```
Expect version `2026-07-v1` and five purposes: four `(required)` and `marketing (optional)`.

**6.8 KYC is refused without consent** — this must be **403**.

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/kyc/run -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"K03\"}"
```
Expect `403`.

**6.9 Give consent** — saves the id in `CID`.

```bash
CID=$(curl -s -X POST localhost:8000/consent -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"purposes\":[\"identity_verification\",\"service_provisioning\",\"regulatory_kyc_record\",\"service_updates\"],\"language\":\"en\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['consent_id'])")
echo "consent: $CID"
```
Expect `consent: <a number>`. Leaving out a required purpose returns 400 with the missing list.

**6.10 Smart KYC on sample applicants** — a fail, a tamper, then a pass.

```bash
for APP in K11 K06 K03; do
  curl -s -X POST localhost:8000/kyc/run -H 'content-type: application/json' -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"$APP\"}" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['applicant'], d['verdict'], [c['code'] for c in d['checks'] if c['status'] in ('FAIL','REVIEW')], d['masked'])"
done
```
Expect:
```
K11 FAIL ['ADDRESS_PROOF_STALE'] {'gstin': '03XXXXXXXXXX1ZZ', 'udyam': 'UDYAM-PB-00-XXXX478'}
K06 FAIL ['GSTIN_CHECKSUM', 'GSTIN_NOT_IN_REGISTRY'] {'gstin': '08XXXXXXXXXX1Z0', 'udyam': 'UDYAM-RJ-00-XXXX157'}
K03 PASS [] {'gstin': '27XXXXXXXXXX1ZP', 'udyam': 'UDYAM-MH-00-XXXX696'}
```
Identifiers always come back masked. Each check also has a plain-language sentence in English and Hindi (`message_en`, `message_hi`).

**6.11 KYC on your own uploaded files** — upload four photos (here K03's, from the repo) as if the owner took them.

```bash
SID2=$(curl -s -X POST localhost:8000/sessions -H 'content-type: application/json' -d '{"language":"en"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")
curl -s -o /dev/null -X POST localhost:8000/consent -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID2\",\"purposes\":[\"identity_verification\",\"service_provisioning\",\"regulatory_kyc_record\",\"service_updates\"],\"language\":\"en\"}"
for DOC in gst_certificate udyam_certificate signatory_id address_proof; do
  curl -s -X POST localhost:8000/kyc/upload -F session_id=$SID2 -F doc_type=$DOC -F file=@backend/data/kyc_documents/K03_$DOC.png \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('uploaded:', d['uploaded'])"
done
curl -s -X POST localhost:8000/kyc/run -H 'content-type: application/json' -d "{\"session_id\":\"$SID2\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['applicant'], d['verdict'])"
```
Expect four `uploaded:` lines, the last one listing all four document types, then `S-xxxxxx PASS` (the applicant
name is built from the session id). These four images are
already in the extraction cache, so no vision-API key is needed. A **new** photo needs `GEMINI_API_KEY` (step 8).

**6.12 Registry lookups** — the mock GST and Udyam registries, masked and rate-limited.

```bash
curl -s localhost:8000/lookup/gstin/32HJJXE5083Y1ZR | python3 -m json.tool
curl -s localhost:8000/lookup/udyam/UDYAM-KL-00-3078801 | python3 -m json.tool
curl -s -o /dev/null -w "bad format -> %{http_code}\n" localhost:8000/lookup/gstin/NOTAGSTIN
```
Expect the GSTIN found with `"status": "Cancelled"`, `"gstin_masked": "32XXXXXXXXXX1ZR"` and the person's name masked
(`"legal_name_masked": "Neha S."`); the Udyam number found (Balaji Dental Care LLP, Kochi, shown as
`UDYAM-KL-00-XXXX801`); and `bad format -> 400`.

**6.13 Order and tracker** — needs a PASS KYC on the session (K03 above was the last run, so it is PASS).

```bash
OID=$(curl -s -X POST localhost:8000/orders -H 'content-type: application/json' -d "{\"session_id\":\"$SID\"}" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['order_id'])")
echo "order: $OID"
curl -s localhost:8000/orders/$OID | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'], d['eta'])"
curl -s -X POST localhost:8000/orders/$OID/advance | python3 -c "import sys,json; d=json.load(sys.stdin); print('after advance:', d['status'])"
```
Expect `order: ORD-XXXXXXXX`, then `PLACED` with a date for each stage (installation about 5 days out for this bundle),
then `after advance: VERIFIED`.
Ordering on a session whose latest KYC is not PASS returns 409.

**6.14 Back-office queue and audit log** — staff only: these endpoints need the `STAFF_PIN` the server was started
with, sent as the `X-Staff-Pin` header (step 5 starts the API with `STAFF_PIN=check-1234`). Without it they return 401.

```bash
curl -s -o /dev/null -w "without the PIN -> %{http_code}\n" "localhost:8000/backoffice/leads?limit=3"
curl -s -H "X-Staff-Pin: check-1234" "localhost:8000/backoffice/leads?limit=3" | python3 -c "import sys,json; [print(r['id'], r['score'], r['business'], '|', r['suggested_action']) for r in json.load(sys.stdin)]"
curl -s -H "X-Staff-Pin: check-1234" "localhost:8000/backoffice/audit?limit=5" | python3 -c "import sys,json; [print(a['action'], '|', a['subject_masked']) for a in json.load(sys.stdin)]"
```
Expect `without the PIN -> 401`, then three leads with a score between 0 and 1 and a suggested next action. Sessions that stopped before an order
(including the ones the tests in step 4 and the blocks above created) rank alongside 200 historical dropped leads
(ids starting with `L`). Then the five latest audit entries, e.g. `lookup.gstin | 32XXXXXXXXXX1ZR found`.
**No full GSTIN appears in the audit log**, only masked ones.

**6.15 Privacy admin: withdraw consent, retention purge**

```bash
curl -s -X DELETE localhost:8000/consent/$SID/$CID | python3 -m json.tool
curl -s -o /dev/null -w "KYC after withdrawal -> %{http_code}\n" -X POST localhost:8000/kyc/run -H 'content-type: application/json' -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"K03\"}"
curl -s -X POST localhost:8000/admin/retention/run -H "X-Staff-Pin: check-1234" -H 'content-type: application/json' -d '{}' | python3 -c "import sys,json; d=json.load(sys.stdin); print('removed:', len(d['removed']), 'kept:', d['kept'])"
```
Expect a `withdrawn_ts` timestamp and a `cleanup` block (uploaded images and the chat transcript are deleted on
withdrawal; the consent URL needs the session id, so nobody can withdraw someone else's consent), then `KYC after withdrawal -> 403`, then `removed: 0` and `kept:` 1 or more (the upload from 6.11
is fresh, so it is kept; rejected uploads are deleted after 30 days, verified ones after 90).
<!-- check:end -->

## 7. Same checks in one command

With the API from step 5 still running:

```bash
SKIP_UI=1 ./scripts/docker_smoke.sh
```
Expect it to end with `ALL API SMOKE CHECKS PASSED (UI checks skipped)`.

## 8. Optional: the live LLM advisor

Stop the API (Ctrl+C in its terminal), add keys, start it without `ADVISOR_OFFLINE`:

```bash
cp .env.example .env        # then edit .env: GROQ_API_KEY=... (free at console.groq.com), GEMINI_API_KEY=... (aistudio.google.com)
cd backend && uvicorn app.main:app --port 8000
```

Repeat 6.5 and 6.6. Now `provider` is `groq` and the reply is written by the model, while the bundle is still decided by
the rules engine. Also try Hindi: `"text":"मेरी साड़ी की दुकान है दिल्ली में"`.
Free-tier note: Groq allows 200,000 tokens a day (about 15 conversations); when it runs out, replies fall back to
`provider: offline` automatically and the quote stays correct.

## 9. Optional: Docker (no Python setup needed)

```bash
docker compose up --build -d --wait     # API on :8000, UI on :8501
./scripts/docker_smoke.sh               # includes the UI checks
docker compose down
```
Expect `ALL DOCKER SMOKE CHECKS PASSED`. The same build and smoke test run on GitHub Actions for every push
(the `ci` badge in the README).

## 10. Optional: test your own scenarios

The engine and advisor checks accept your own JSON files, so you can test cases we did not think of.

**Profile scenario** (rules engine only, instant). Save as `my_scenarios/s1.json`:

```json
{"name": "my clinic, 4 staff, Mumbai, wants Fibre 1G",
 "profile": {"business_type": "Dental clinic", "employee_count": 4, "num_sites": 1, "city": "Mumbai", "has_gstin": true, "requested_products": ["P03"]},
 "expect_excludes": {"P03": "MIN_EMPLOYEES"}, "expect_includes": ["P02"]}
```
Run: `cd backend && python scripts/run_scenarios.py ../my_scenarios/`

**Conversation scenario** (the chat advisor, live or offline). Save as `my_chats/c1.json`:

```json
{"name": "tailor asks for a firewall",
 "turns": ["Tailoring shop in Delhi, 6 people, one shop, GST registered", "I want a managed firewall"],
 "expect_excludes": {"P21": "MIN_EMPLOYEES"}}
```
Run: `cd backend && ADVISOR_OFFLINE=1 python scripts/run_llm_scenarios.py ../my_chats/ --allow-offline`
(drop `ADVISOR_OFFLINE=1 ... --allow-offline` to use the live LLM). Both scripts document all `expect_*` fields at the top of the file.

## 11. Optional: the app itself

```bash
./run_local.sh            # API on :8000 and the phone-shaped UI on :8501
```
Open http://localhost:8501. Enter any Indian mobile number: a fresh 6-digit code is generated for every request and, with no SMS
provider configured, shown on screen as a labelled demo SMS. For the back office (sidebar → backoffice) set a PIN first:
`STAFF_PIN=your-pin ./run_local.sh`.
The click-through is in [demo-script.md](demo-script.md).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python3.13: command not found` | install Python 3.13 (python.org or `brew install python@3.13`), or use `python3` if `python3 --version` shows 3.13 |
| `Address already in use` on port 8000 | another server is running: stop it, or start on another port (`--port 8010`) and use that port in every curl |
| `curl: (7) Failed to connect` | the API from step 5 is not running, or is still starting |
| `KeyError: 'session_id'` or empty `SID` | step 6.5 failed; run it again and check that `echo $SID` prints an id |
| KYC returns **503** | a brand-new image needs the vision API; set `GEMINI_API_KEY` or use a sample applicant |
| advisor `provider: offline` with keys set | LLM quota exhausted or key wrong; the quote is still correct |
| Windows quoting errors in curl | use Git Bash or WSL, or use `http://localhost:8000/docs` → "Try it out" |
