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
echo 'all tests passed'
