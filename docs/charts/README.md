# Charts for the deck

Generated from `backend/data/smb_leads.csv` by `backend/scripts/make_charts.py` (5,000 leads, 2026-04-01 to 2026-06-30).
Every number below is in `numbers.json`; regenerate with `python scripts/make_charts.py` from `backend/` (needs `pip install matplotlib`, used only by the chart scripts).

| Chart | Headline | Use on slide |
|---|---|---|
| 01_activation_by_source | Referral 14.8% vs field sales 7.3% vs WhatsApp campaign 2.8% | Problem / where to acquire |
| 02_payback_by_segment | Micro retail payback 8.0 months; multi-site 0.5; manufacturers 0.8 | Business case / redeploy field force |
| 03_drop_reasons | 48.5% of drops are the sales process | Problem |
| 04_gst_divider | 9.6% vs 2.0%; 600 no-GST leads asked for GST-only products (2.3%) | Why the engine has a GST-free path |
| 05_asked_vs_sold | AirFiber asked 719× sold 9×; WhatsApp API 827/54 | Advisor sells what is asked, within rules |
| 06_days_to_activation | median 17 days today → target ≤ 5 | Tracker / instant quote |
| 07_churn_vs_calls | churn 5.9% at 1 call → 27.9% at 5+ | Why the tracker matters |
| 08_language_mix | Hindi + English = 66.1% | Language scope decision |

Micro retail via field sales: blended CAC ₹53,026 per activation for ₹2,619/month (27 activations from 894 leads).
