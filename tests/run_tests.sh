#!/usr/bin/env bash
# Offline logic tests. Fixture timestamps are templated (__H<hours>__) and rendered relative to now.
set -e; cd "$(dirname "$0")"
python3 - << 'PY'
import re
from datetime import datetime, timedelta, timezone
t = open('fixture_new_pools.template.json').read()
now = datetime.now(timezone.utc)
t = re.sub(r'__H([0-9.]+)__', lambda m: (now - timedelta(hours=float(m.group(1)))).strftime('%Y-%m-%dT%H:%M:%SZ'), t)
open('/tmp/fixture_new_pools.json','w').write(t)
PY
cd ../scripts
python3 discover.py --fixture /tmp/fixture_new_pools.json --rules ../rules.json --out /tmp/c.json > /tmp/o.txt && grep -q '"candidates": 1' /tmp/o.txt
python3 risk.py --fixture ../tests/fixture_risk.json --rules ../rules.json --in /tmp/c.json --out /tmp/r.json > /tmp/o.txt && grep -q NEEDS_LIVE_VERIFICATION /tmp/o.txt
python3 cost.py --liquidity 25000 --rules ../rules.json > /tmp/o.txt && grep -q gross_move_needed /tmp/o.txt
python3 - << 'PY2'
# dedupe: same mint twice -> one slot; different mint, same symbol -> kept, flagged as copycat
from datetime import datetime, timedelta, timezone
import risk
from discover import apply_filters
t = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')
mk = lambda pool, mint, vol: {"pool_address": pool, "token_address": mint, "token_symbol": "HYPE", "created_at": t,
     "liquidity_usd": 50000, "volume_h1_usd": vol, "txns_h1": 500, "sells_h1": 200}
f = {"age_hours_min": 1, "age_hours_max": 24, "min_liquidity_usd": 15000, "min_volume_h1_usd": 5000, "min_txns_h1": 60, "max_candidates": 3}
kept, excl = apply_filters([mk("P1", "M1", 9e6), mk("P2", "M1", 1e6), mk("P3", "M2", 5e6)], f)
assert [k["pool_address"] for k in kept] == ["P1", "P3"], kept
assert kept[0]["same_symbol_other_mints"] == ["M2"] and excl[0]["exclude_reasons"] == ["duplicate_token_pool"]
# rpc: every endpoint's failure reason is kept
risk.RPCS = ["https://a.example", "https://b.example"]
risk.post_json = lambda url, payload: (None, "HTTP 400 " + url)
_, err = risk.rpc("getTokenLargestAccounts", ["x"])
assert "a.example" in err and "b.example" in err, err
print("dedupe + rpc error tests ok")
PY2
echo 'all tests passed'
