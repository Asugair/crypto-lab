#!/usr/bin/env bash
# One cycle: discover -> risk -> cost table -> report skeleton. No trading. Exit 0 even with zero candidates.
set -u; cd "$(dirname "$0")"
mkdir -p data
cd scripts
python3 discover.py --rules ../rules.json --out ../data/candidates.json --pages "${PAGES:-5}"
python3 risk.py --rules ../rules.json --in ../data/candidates.json --out ../data/risk.json
cd ..
python3 - << 'PY'
import json, subprocess
c = json.load(open("data/candidates.json")); r = json.load(open("data/risk.json"))
rows = []
for cand, rev in zip(c["candidates_list"], r["reviews"]):
    cost = json.loads(subprocess.check_output(["python3","scripts/cost.py","--liquidity",str(cand["liquidity_usd"]),"--rules","rules.json"]))
    gth = rev.get("holders_geckoterminal") or {}
    # everything the agent needs for the manual holder step, so it never has to open candidates.json/risk.json
    rows.append({"pair": cand["pair"], "verdict": rev["verdict"], "reasons": rev["reject_reasons"], "missing": rev["missing_checks"],
                 "cost_pct_est": cost["total_cost_pct_roundtrip"], "url": cand["source_url"],
                 "token_address": cand["token_address"], "pool_address": cand["pool_address"], "dex": cand.get("dex"),
                 "age_hours": cand.get("age_hours"), "liquidity_usd": round(cand["liquidity_usd"]),
                 "volume_h1_usd": round(cand["volume_h1_usd"]), "txns_h1": cand["txns_h1"], "sells_h1": cand["sells_h1"],
                 "price_change_h1_pct": cand.get("price_change_h1_pct"), "fdv_usd": cand.get("fdv_usd"),
                 "found_via": cand.get("found_via"), "same_symbol_other_mints": cand.get("same_symbol_other_mints", []),
                 "gt_holders_count": gth.get("count"), "gt_top10_incl_pools_pct": gth.get("top10_incl_pools_pct"),
                 "check_errors": rev.get("check_errors", []), "manual_holder_check_url": rev.get("manual_holder_check_url")})
json.dump({"cycle_at": c["fetched_at"], "discovery_status": c["status"], "scanned": c["scanned"], "excluded": c["excluded"],
           "exclusion_summary": c["exclusion_summary"], "discovery_errors": c.get("errors", []),
           "stale_for_scalping_after_min": 60, "candidates": rows}, open("data/latest.json","w"), indent=2)
print(json.dumps(rows, indent=1, ensure_ascii=False))
PY
