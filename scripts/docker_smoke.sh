#!/usr/bin/env bash
# Smoke test for `docker compose up`: API health, the Phase-6 checkpoint, the consent gate, a sample KYC run,
# the UI's health, and the UI container reaching the API over the compose network.
# Usage (repo root, stack already up):  ./scripts/docker_smoke.sh      Exit 0 = all good.
# Against a plain local API (no Docker, no UI):  SKIP_UI=1 ./scripts/docker_smoke.sh   (API defaults to localhost:8000)
set -euo pipefail
API=${API:-http://localhost:8000}
UI=${UI:-http://localhost:8501}
fail() { echo "FAIL: $*"; exit 1; }
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print(eval(sys.argv[1], {'d': d}))" "$1"; }

echo "== API /health"
curl -fsS "$API/health" | tee /dev/stderr | json "d['ok'] and d['catalogue_products'] == 25" | grep -q True || fail "health"

echo; echo "== engine checkpoint: kirana, no GST, wants WhatsApp -> P15 excluded GSTIN_REQUIRED"
curl -fsS -X POST "$API/engine/recommend" -H 'content-type: application/json' \
  -d '{"business_type":"Kirana","employee_count":2,"num_sites":1,"city":"Lucknow","has_gstin":false,"needs":["whatsapp_customers"]}' \
  | json "[(e['product_id'], e['reason']) for e in d['excluded']] == [('P15', 'GSTIN_REQUIRED')]" | grep -q True || fail "recommend"
echo ok

echo "== consent gate: KYC without consent must be 403"
SID=$(curl -fsS -X POST "$API/sessions" -H 'content-type: application/json' -d '{"language":"en"}' | json "d['session_id']")
CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API/kyc/run" -H 'content-type: application/json' -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"K03\"}")
[ "$CODE" = "403" ] || fail "expected 403 without consent, got $CODE"
echo ok

echo "== consent then sample KYC K03 -> PASS, K11 -> FAIL"
curl -fsS -X POST "$API/consent" -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"purposes\":[\"identity_verification\",\"service_provisioning\",\"regulatory_kyc_record\",\"service_updates\"],\"language\":\"en\"}" >/dev/null
curl -fsS -X POST "$API/kyc/run" -H 'content-type: application/json' -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"K03\"}" \
  | json "d['verdict']" | grep -qx PASS || fail "K03 should PASS"
curl -fsS -X POST "$API/kyc/run" -H 'content-type: application/json' -d "{\"session_id\":\"$SID\",\"sample_applicant\":\"K11\"}" \
  | json "d['verdict']" | grep -qx FAIL || fail "K11 should FAIL"
echo ok

echo "== advisor chat answers (offline path if no LLM key in the container)"
curl -fsS -X POST "$API/advisor/chat" -H 'content-type: application/json' \
  -d "{\"session_id\":\"$SID\",\"text\":\"Kirana store in Lucknow, 2 people, one shop, no GST, customers order on WhatsApp\"}" \
  | json "bool(d['text']) and d['recommendation'] is not None" | grep -q True || fail "advisor"
echo ok

if [ "${SKIP_UI:-0}" = "1" ]; then
  echo; echo "ALL API SMOKE CHECKS PASSED (UI checks skipped)"
  exit 0
fi

echo "== UI health"
curl -fsS "$UI/_stcore/health" | grep -q ok || fail "ui health"
echo ok

echo "== UI container reaches the API over the compose network"
docker compose exec -T frontend python -c "import urllib.request,json; d=json.load(urllib.request.urlopen('http://backend:8000/health', timeout=5)); assert d['ok']; print('ok')" \
  || fail "frontend -> backend"

echo; echo "ALL DOCKER SMOKE CHECKS PASSED"
