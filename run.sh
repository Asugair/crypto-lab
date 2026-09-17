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
    rows.append({"pair": cand["pair"], "verdict": rev["verdict"], "reasons": rev["reject_reasons"], "missing": rev["missing_checks"],
                 "cost_pct_est": cost["total_cost_pct_roundtrip"], "url": cand["source_url"]})
json.dump({"cycle_at": c["fetched_at"], "discovery_status": c["status"], "scanned": c["scanned"], "excluded": c["excluded"],
           "exclusion_summary": c["exclusion_summary"], "candidates": rows}, open("data/latest.json","w"), indent=2)
print(json.dumps(rows, indent=1, ensure_ascii=False))
PY
