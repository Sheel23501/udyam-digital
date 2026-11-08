# Privacy & security note (DPDP Act 2023) — Project Udyam Digital

One page. Each line is a decision and where it lives in the prototype, so it can be checked, not just read.

**Roles.** Accel Business is the Data Fiduciary. The LLM provider and the vision provider are Data Processors acting on
instruction (business facts and document images respectively). The cloud host is a processor. The business owner is the Data Principal.

| Principle | Decision | Where it is implemented |
|---|---|---|
| **Notice & consent** | Itemised, plain-language notice in the owner's language *before* any document is collected; four required purposes (identity verification, service provisioning, regulatory KYC record, service updates) and one optional (marketing); stored with timestamp, language, notice version; withdrawable from the tracker screen. | `privacy/consent.py`, `GET /consent/notice`, `POST /consent`, `DELETE /consent/{id}`; UI `ui/steps/consent.py`, `ui/steps/tracker.py` |
| **Consent is enforced, not displayed** | Document upload and verification return **HTTP 403** without an active consent for the session. | `routers/consent.py: require_consent` used by `POST /kyc/upload` and `POST /kyc/run`; test `test_kyc_run_refuses_without_consent_then_passes_sample_k03` |
| **Purpose limitation** | KYC documents are used only for verification. Advisor profile and KYC store are separate tables; the recommendation never reads KYC data; marketing never reads documents. | tables `sessions` vs `kyc_applications`; engine takes only the profile |
| **Data minimisation** | Advisor asks for five facts; KYC accepts the GSTIN path *or* the Udyam-only path; no Aadhaar; registry lookups return name/status/state/date only; only the document image leaves the boundary (no CRM data, no profile). | `advisor/tools.py REQUIRED`, `kyc/pipeline.py udyam_only_path`, `routers/lookup.py`, `kyc/extract.py` |
| **Images do not move before consent** | Upload itself is consent-gated, so no image reaches our server, let alone a processor, before the notice is accepted. | `POST /kyc/upload` → `require_consent` |
| **Mobile verification** | A fresh random 6-digit code per request; only an HMAC of it is stored; it expires in 5 minutes, works once, and locks after 5 wrong tries; resend cooldown and hourly caps per number and per client stop SMS-bombing. The phone number is stored only as an HMAC plus a masked form (`XXXXXX3210`); the audit log never sees the number or the code. | `auth/otp.py`, `auth/sms.py`, `POST /auth/otp/request`, `POST /auth/otp/verify`; tests `tests/test_otp.py` |
| **Masking & logging** | GSTIN shown as `27XXXXXXXXXX1ZP`, Udyam as `UDYAM-DL-00-XXXX547`, names as "Neha B."; every audit subject is masked before it is written; no document bytes or raw identifiers in logs. | `privacy/masking.py`, `privacy/audit.py`, `kyc/report.py`; test `test_audit_log_never_contains_raw_identifiers` |
| **Retention & erasure** | Rejected (FAIL/REVIEW) applications: images deleted after 30 days. Verified: images deleted after 90 days, extracted fields kept for the regulatory period. Erasure request deletes images and transcript at once and keeps only the regulatory KYC record. | `privacy/retention.py`, `POST /admin/retention/run`, `POST /admin/erase/{session_id}`; back-office "Privacy admin" tab |
| **Accuracy & fairness** | A photo problem is REVIEW ("re-take the photo"), never FAIL; FAIL always carries the reason and a "talk to a human" path; the propensity score only prioritises outreach and never denies service. | `kyc/gates.py`, `kyc/report.py next_step`, `backoffice/leads.py` |
| **Security** | TLS in transit (platform); secrets in environment, never in the repo; uploads limited to PNG/JPG ≤ 8 MB; lookup endpoints rate-limited (30/min); back-office behind a staff PIN (prototype) → SSO and least-privilege roles in production; session ids are random, OTP-bound. | `routers/kyc.py`, `routers/lookup.py`, `pages/backoffice.py` |
| **Breach readiness** | Audit log gives who-saw-what; runbook: contain → assess → notify the Data Protection Board and affected principals within the DPDP Rules timelines → remediate. | `GET /backoffice/audit` |
| **Residency & processors** | Production deploys in India regions; processor contracts with the LLM/vision vendors; the architecture is provider-agnostic (OpenAI-compatible chain) so a vendor can be swapped without touching the journey. | `llm/providers.py` |

**What is mocked in the prototype:** the GSTN and Udyam registries (CSV mocks; format and checksum validation are real), OTP delivery (the OTP service itself
is real; without an SMS gateway the code is shown on screen as a labelled demo SMS), notifications. Production adapters: GSTN/GSP API, Udyam API, DigiLocker for document pull, eSign for the order, an SMS/WhatsApp
provider for updates.

**Owner-facing summary (shown in the app):** "We use your documents only to verify your business and set up your service. We keep the
record the law requires, delete the rest on a schedule, mask your identifiers everywhere, and you can withdraw at any time."
