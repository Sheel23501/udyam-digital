# Demo script (3 minutes) and live-scenario playbook

Record on the deployed URL in Chrome device emulation (iPhone viewport) or on a real phone, Hindi + English captions.
Open the app 10 minutes before so it is warm. Keep `docs/demo-transcripts.md` open as a fallback script.

| Time | On screen | Say |
|---|---|---|
| 0:00–0:20 | Chart 03 (drop reasons), then chart 02 (payback) | "4,632 of 5,000 leads dropped. Half of them because a human was in the way: unreachable, no time for a visit, quote too slow. And field sales on a micro shop costs ₹53,000 to win ₹2,600 a month. So we built a journey with no salesperson in it." |
| 0:20–1:05 | Phone, Hindi. Tap example chip 1 (sari shop, Delhi, 5 staff, 2 shops, GST, card machine drops, cameras). Card appears. | "The owner answers in Hindi. The advisor asks four questions, not forty. The card is not the model's opinion: a rules engine decided every item. Two fibre lines, failover so the card machine never drops, billing, four cameras, one monthly number. And it says what it left out and why." |
| 1:05–1:30 | **See my price** → toggle a camera count, switch an item off; price updates; a locked item shows its reason. | "Every toggle is re-checked against the same rules. Nothing can be sold that the owner isn't eligible for." |
| 1:30–2:15 | **Continue** → consent (Hindi) → tick 4 → **Use a sample applicant** → K11 → Verify: FAIL (bill from October 2025) → Try another → K06 → FAIL (checksum / tampered digit) → K03 → PASS, masked GSTIN, registry Active. | "Before any document is read, the owner sees exactly what we collect and why: DPDP consent in their language, and the API refuses documents without it. Then Smart KYC reads four photos and checks the registries live. It catches a stale bill, a tampered GSTIN, a cancelled registration. Last quarter 22 customers were activated with a non-active GSTIN. With this: zero." |
| 2:15–2:35 | **Place my order** → tracker with dates → **Advance stage** → toast | "No status calls. Every step has a date. In the data, customers who had to call five times churned at 28%; those who called once, 6%." |
| 2:35–2:55 | Sidebar → backoffice → staff PIN → queue | "Leads the journey can't close go to a scored queue, so the field team spends its day on the ₹31,000-a-month multi-site customer, not the ₹2,500 kirana." |
| 2:55–3:00 | README / scenario runner | "Everything is tested: over 2,000 tests, 30 scenario fixtures, a KYC answer key. Drop your 15 scenarios in and run them." |

## Live scenario playbook (judges type, you narrate)

- **The model is slow or Groq is throttled:** the reply says "assistant is briefly unavailable" and the quote still appears. Say: "the
  engine never depends on the model; the prose does." Carry on.
- **Judge asks for an ineligible product** (firewall for 6 staff, SD-WAN for 2 sites, WhatsApp API without GST): point at the
  *left out and why* line, then at the locked toggle on the quote page.
- **Judge changes a fact mid-chat** ("actually two shops"): the card re-computes; show the quantities doubling.
- **Judge types Hinglish or a regional language:** Hinglish is answered in Hinglish; Tamil/Bengali get English plus the offer of Hindi.
- **Judge uploads their own photo:** it goes through gates → extraction → validators; a screenshot of a sample bill still FAILs for the
  right reason (we tested a re-encoded K11 bill). If the vision quota is out, the API says so (503) and the sample path still works.
- **"Is this cache-only?"** No: the sha256 cache only short-cuts identical images; `scripts/kyc_report.py --no-cache` re-extracts.
- **"Where does the LLM decide?"** Nowhere. `engine/rules.py` decides; the advisor's tools call it; the UI renders engine JSON.

## Commands to have in a terminal

```bash
cd backend
python scripts/run_scenarios.py                       # 30/30 profile scenarios
python scripts/kyc_report.py --key tests/kyc_answer_key_images.json   # 12/12
ADVISOR_OFFLINE=1 python scripts/run_llm_scenarios.py --allow-offline # 16/16 with the network dead
pytest -q                                             # ~2,050 tests
```
