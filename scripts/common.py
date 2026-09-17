"""Shared helpers. Stdlib only, no keys, no wallets."""
import json, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

UA = {"User-Agent": "crypto-lab/1.0 (research, no trading)", "Accept": "application/json"}

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_json(url, retries=3, timeout=20):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == 429:
                time.sleep(3 * (i + 1)); continue
            break
        except Exception as e:
            last = str(e); time.sleep(1)
    return None, last

def post_json(url, payload, timeout=20):
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={**UA, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode()), None
    except Exception as e:
        return None, str(e)

def load_rules(path="rules.json"):
    with open(path) as f:
        return json.load(f)

def save(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)

def hours_since(iso):
    t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - t).total_seconds() / 3600
