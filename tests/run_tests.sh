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
risk.post_json = lambda url, payload, timeout=20: (None, "HTTP 400 " + url)
_, err = risk.rpc("getTokenLargestAccounts", ["x"])
assert "a.example" in err and "b.example" in err, err
# brand gate: whole-word symbol/name match only
from discover import brand_hit
B = ["OPENAI", "GPT", "META"]
assert brand_hit({"token_symbol": "OpenAI", "token_name": "x"}, B) == "OPENAI"
assert brand_hit({"token_symbol": "AGENT", "token_name": "GPT Agent"}, B) == "GPT"
assert brand_hit({"token_symbol": "GPTX", "token_name": "Metaverse cat"}, B) is None
f["reject_brand_impersonation"] = B
kept, excl = apply_filters([{**mk("P9", "M9", 9e6), "token_symbol": "OPENAI"}], f)
assert not kept and excl[0]["exclude_reasons"] == ["brand_impersonation"]
print("dedupe + rpc error + brand tests ok")
PY2
python3 - << 'PY3'
# track v2: price outcome from OHLCV, evaluated only once a pool is >24h old
import json, os, subprocess, tempfile
from datetime import datetime, timedelta, timezone
import track
d = tempfile.mkdtemp(); os.makedirs(f"{d}/h")
t0 = (datetime.now(timezone.utc) - timedelta(hours=30)).replace(minute=0, second=0, microsecond=0)
iso = lambda t: t.strftime('%Y-%m-%dT%H:%M:%SZ')
cand = lambda name: {"pair": f"{name} / SOL", "verdict": "unverified", "cost_pct_est": 0.66, "url": f"https://x/pools/{name}"}
json.dump({"cycle_at": iso(t0), "candidates": [cand("OK"), cand("SPIKE"), cand("DEAD")]}, open(f"{d}/h/a.json", "w"))
json.dump({"cycle_at": iso(t0 + timedelta(hours=25)), "candidates": [cand("NEW")]}, open(f"{d}/h/b.json", "w"))
T = int(t0.timestamp())
px = lambda k: 2.0 if 4 <= k < 24 else (0.4 if 24 <= k < 96 else (1.1 if k == 96 else 1.0))  # +1h 2.0, +6h 0.4, +24h 1.1
normal = [[T + k*900, px(k), px(k) * 1.1, px(k) * 0.9, px(k), 10] for k in range(97)]
spike = [c[:] for c in normal]; spike[10][2] = 1000.0                                          # one bad print
dead = normal[:9]                                                                               # quiet after 2h
fx = {n: {"data": {"attributes": {"ohlcv_list": c[::-1]}}} for n, c in (("OK", normal), ("SPIKE", spike), ("DEAD", dead))}
json.dump(fx, open(f"{d}/fx.json", "w"))
subprocess.run(["python3", "track.py", "--history", f"{d}/h", "--out", f"{d}/t.json", "--rules", "../rules.json",
                "--fixture", f"{d}/fx.json"], check=True, capture_output=True)
r = json.load(open(f"{d}/t.json")); rows = {x["pair"].split()[0]: x for x in r["rows"]}
assert r["pending_under_24h_or_retry"] == 1 and set(rows) == {"OK", "SPIKE", "DEAD"}, r
ok = rows["OK"]
assert ok["status"] == "ok" and (ok["ret_1h_pct"], ok["ret_6h_pct"], ok["ret_24h_pct"]) == (100.0, -60.0, 10.0), ok
assert (ok["max_up_close_24h_pct"], ok["max_down_close_24h_pct"]) == (100.0, -60.0), ok
assert rows["SPIKE"]["status"] == "suspect_data", rows["SPIKE"]
dd = rows["DEAD"]
assert dd["status"] == "ok" and dd["ret_1h_pct"] == 100.0 and dd["ret_6h_pct"] is None and dd["stopped_before_6h"], dd
sm = r["summary"]
assert sm["suspect_data"] == 1 and sm["ret_6h"]["n_priced"] == 1 and sm["ret_6h"]["n_stopped_trading"] == 1, sm
# detection 5 min into a candle (the 2026-09-24 crash): entry candle starts before t0, window must not be empty
row2 = track.evaluate({"detected_at": iso(t0 + timedelta(minutes=5))}, normal)
assert row2["status"] == "ok" and row2["max_up_close_24h_pct"] is not None, row2
# rows from an older version are re-evaluated
json.dump({"rows": [{**rows["OK"], "version": 1}]}, open(f"{d}/t.json", "w"))
subprocess.run(["python3", "track.py", "--history", f"{d}/h", "--out", f"{d}/t.json", "--rules", "../rules.json",
                "--fixture", f"{d}/fx.json"], check=True, capture_output=True)
assert all(x["version"] == track.VERSION for x in json.load(open(f"{d}/t.json"))["rows"])
print("track tests ok")
PY3
echo 'all tests passed'
