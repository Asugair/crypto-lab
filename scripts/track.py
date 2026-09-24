"""Price outcome of every candidate after discovery: +1h / +6h / +24h and the 24h range.
This is NOT a trade simulation and never touches data/ledger.csv. It answers one question for the joint review:
"after the filters picked a pool, what did its price do?" Candidates come from data/history/*.json (cycle_at =
detection time). Each pool is evaluated once, when it is at least 24h old, from GeckoTerminal 15-minute OHLCV
(keyless). Prices are candle opens, so every number is +/-15 min; the detection price is itself optimistic because
a real entry would come later than the scan.
Usage: python scripts/track.py [--history data/history] [--out data/tracking.json] [--rules rules.json] [--fixture f.json]"""
import argparse, glob, json, os, statistics, time
from datetime import datetime, timezone
from common import get_json, now_iso, load_rules, save

OHLCV = ("https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute"
         "?aggregate=15&before_timestamp={before}&limit=100&currency=usd&token=base")
CANDLE, MAX_GAP = 900, 3600  # 15-minute candles; no trade for an hour around a checkpoint = no price
CHECKPOINTS = {"1h": 3600, "6h": 6 * 3600, "24h": 24 * 3600}

def ts(iso):
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())

def detections(history_dir):
    """First sighting of each pool across all saved scans."""
    seen = {}
    for f in sorted(glob.glob(os.path.join(history_dir, "*.json"))):
        d = json.load(open(f))
        for c in d.get("candidates", []):
            pool = c.get("pool_address") or c["url"].rstrip("/").split("/")[-1]
            if pool not in seen:
                seen[pool] = {"pool_address": pool, "pair": c["pair"], "detected_at": d["cycle_at"],
                              "verdict_at_detection": c["verdict"], "cost_pct_est": c.get("cost_pct_est"),
                              "url": c["url"], "scan_file": os.path.basename(f)}
    return seen

def price_at(candles, t):
    """Open of the first candle starting at or after t (no look-ahead). None if the gap is over MAX_GAP."""
    for c in candles:
        if c[0] >= t - CANDLE // 2:
            return (c[1], c[0]) if c[0] - t <= MAX_GAP else (None, c[0])
    return None, None

def evaluate(det, candles):
    t0 = ts(det["detected_at"])
    candles = sorted(c for c in candles if t0 - CANDLE <= c[0] <= t0 + CHECKPOINTS["24h"])
    p0, t_p0 = price_at(candles, t0)
    if not candles or not p0:
        return {"status": "no_price_at_detection"}
    out = {"status": "ok", "price_at_detection": p0}
    for k, dt in CHECKPOINTS.items():
        p, _ = price_at(candles, t0 + dt)
        out[f"ret_{k}_pct"] = round(100 * (p / p0 - 1), 1) if p else None
    window = [c for c in candles if c[0] >= t_p0]  # from the entry candle, which may start up to 7.5 min before t0
    out["max_up_24h_pct"] = round(100 * (max(c[2] for c in window) / p0 - 1), 1)
    out["max_down_24h_pct"] = round(100 * (min(c[3] for c in window) / p0 - 1), 1)
    out["last_trade_candle_h"] = round((window[-1][0] - t0) / 3600, 1)
    return out

def summarize(rows, target_net_pct):
    ok = [r for r in rows if r.get("status") == "ok"]
    def stat(k):
        v = [r[k] for r in ok if r.get(k) is not None]
        return {"n": len(v), "median_pct": round(statistics.median(v), 1) if v else None,
                "share_up_pct": round(100 * sum(x > 0 for x in v) / len(v)) if v else None}
    beat = [r for r in ok if r.get("ret_24h_pct") is not None and r["cost_pct_est"] is not None]
    return {"evaluated": len(rows), "with_prices": len(ok), "no_price": len(rows) - len(ok),
            **{f"ret_{k}": stat(f"ret_{k}_pct") for k in CHECKPOINTS},
            "share_24h_above_target_plus_cost_pct": round(100 * sum(
                r["ret_24h_pct"] > target_net_pct + r["cost_pct_est"] for r in beat) / len(beat)) if beat else None,
            "share_fell_50pct_within_24h": round(100 * sum(r["max_down_24h_pct"] <= -50 for r in ok) / len(ok)) if ok else None,
            "caveat": "Price observations, not trades. Detection price is optimistic (a real entry comes later); "
                      "costs are the model Estimate; +/-15 min resolution."}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--history", default="data/history"); ap.add_argument("--out", default="data/tracking.json")
    ap.add_argument("--rules", default="rules.json"); ap.add_argument("--fixture")
    a = ap.parse_args()
    target = load_rules(a.rules)["session_rules"]["target_net_pct"]
    fixture = json.load(open(a.fixture)) if a.fixture else None
    prev = json.load(open(a.out)).get("rows", []) if os.path.exists(a.out) else []
    done = {r["pool_address"]: r for r in prev if r.get("status") in ("ok", "no_price_at_detection")}
    rows, pending, errors, now = [], 0, [], time.time()
    for pool, det in detections(a.history).items():
        if pool in done: rows.append(done[pool]); continue
        if now - ts(det["detected_at"]) < CHECKPOINTS["24h"] + CANDLE: pending += 1; continue
        if fixture is not None:
            data, err = fixture.get(pool), None
        else:
            data, err = get_json(OHLCV.format(pool=pool, before=ts(det["detected_at"]) + CHECKPOINTS["24h"] + CANDLE))
            time.sleep(3.0)
        if err or not data:
            errors.append({"pool": pool, "error": err or "empty"}); pending += 1; continue  # retried next run
        candles = (((data.get("data") or {}).get("attributes") or {}).get("ohlcv_list")) or []
        try:
            out = evaluate(det, [[int(c[0])] + [float(x) for x in c[1:5]] for c in candles])
        except Exception as e:  # one odd pool must not throw away the whole run (2026-09-24 17:55 run lost all 48)
            errors.append({"pool": pool, "error": f"evaluate: {e!r}"}); pending += 1; continue
        rows.append({**det, **out, "evaluated_at": now_iso(), "source": "GeckoTerminal OHLCV 15m"})
    res = {"updated_at": now_iso(), "pending_under_24h_or_retry": pending, "errors": errors,
           "summary": summarize(rows, target), "rows": rows}
    save(a.out, res)
    print(json.dumps({k: res[k] for k in ("updated_at", "pending_under_24h_or_retry", "summary")}, indent=1, ensure_ascii=False))

if __name__ == "__main__": main()
