"""Forward price snapshots of every candidate, replacing historical-candle tracking (track.py, removed 2026-09-24:
old 15m candles came back sparse and survivor-only, so its numbers could not be trusted).
Each run: add the new candidates with the live price seen at discovery, then read the CURRENT price, liquidity and
1h volume of every pool detected in the last 7 days in one GeckoTerminal /pools/multi call per 30 pools.
Both prices are observed directly; nothing is reconstructed. These are price observations, NOT trades: never write
them to the ledger or report them as P&L. The detection price is optimistic (a real entry comes later).
Usage: python scripts/snapshot.py [--latest data/latest.json] [--out data/snapshots.json] [--rules rules.json] [--fixture f.json]"""
import argparse, json, os, statistics, time
from datetime import datetime, timezone
from common import get_json, now_iso, load_rules, save

MULTI = "https://api.geckoterminal.com/api/v2/networks/solana/pools/multi/{}"
KEEP_H, DAY_MIN_H, DAY_MAX_H = 7 * 24, 12, 48  # "about a day" = the observation closest to 24h within 12-48h
DEAD_LIQ_USD, DEAD_LIQ_SHARE = 1000, 0.2       # pool gone, or liquidity under $1k / under 20% of what we saw

def hours(a, b):
    f = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (f(b) - f(a)).total_seconds() / 3600

def parse_multi(payload):
    out = {}
    for p in (payload or {}).get("data", []):
        a = p.get("attributes", {})
        out[a.get("address")] = {"price": float(a.get("base_token_price_usd") or 0) or None,
                                 "liquidity_usd": float(a.get("reserve_in_usd") or 0),
                                 "volume_h1_usd": float((a.get("volume_usd") or {}).get("h1") or 0)}
    return out

def add_new(pools, latest):
    for c in latest.get("candidates", []):
        pool = c.get("pool_address")
        if pool and pool not in pools and c.get("price_usd"):
            pools[pool] = {"pair": c["pair"], "token_address": c.get("token_address"), "detected_at": latest["cycle_at"],
                           "price0": c["price_usd"], "liquidity0_usd": c.get("liquidity_usd"),
                           "cost_pct_est": c.get("cost_pct_est"), "verdict_at_detection": c["verdict"], "obs": []}

def record(pools, live, at):
    for pool, p in pools.items():
        if hours(p["detected_at"], at) > KEEP_H or hours(p["detected_at"], at) < 0.5: continue
        o = live.get(pool)
        p["obs"].append({"at": at, "h": round(hours(p["detected_at"], at), 1), "missing": o is None,
                         **({"ret_pct": round(100 * (o["price"] / p["price0"] - 1), 1) if o["price"] else None,
                             "liquidity_usd": round(o["liquidity_usd"]), "volume_h1_usd": round(o["volume_h1_usd"])} if o else {})})

def dead(p, o):
    return o["missing"] or o.get("liquidity_usd", 0) < max(DEAD_LIQ_USD, DEAD_LIQ_SHARE * (p.get("liquidity0_usd") or 0))

def summarize(pools, target_net_pct):
    day = []
    for p in pools.values():
        near = [o for o in p["obs"] if DAY_MIN_H <= o["h"] <= DAY_MAX_H]
        if near: day.append((p, min(near, key=lambda o: abs(o["h"] - 24))))
    alive = [(p, o) for p, o in day if not dead(p, o) and o.get("ret_pct") is not None]
    rets = [o["ret_pct"] for _, o in alive]
    return {"tracked": len(pools), "with_day_observation": len(day),
            "dead_or_drained_by_day": len(day) - len(alive),
            "day_median_ret_pct_alive": round(statistics.median(rets), 1) if rets else None,
            # a dead/drained pool counts as a miss, not as missing data
            "day_share_above_target_plus_cost_pct": round(100 * sum(
                o["ret_pct"] > target_net_pct + (p.get("cost_pct_est") or 0) for p, o in alive) / len(day)) if day else None,
            "day_share_down_50pct_or_dead": round(100 * (sum(o["ret_pct"] <= -50 for _, o in alive) + len(day) - len(alive))
                                                  / len(day)) if day else None,
            "caveat": "Observed prices at discovery and at later scans; not trades. Detection price is optimistic "
                      "(a real entry comes later). Dead = pool gone or liquidity < max($1k, 20% of first seen)."}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--latest", default="data/latest.json"); ap.add_argument("--out", default="data/snapshots.json")
    ap.add_argument("--rules", default="rules.json"); ap.add_argument("--fixture")
    a = ap.parse_args()
    target = load_rules(a.rules)["session_rules"]["target_net_pct"]
    state = json.load(open(a.out)) if os.path.exists(a.out) else {"pools": {}}
    pools, errors, at = state["pools"], [], now_iso()
    add_new(pools, json.load(open(a.latest)))
    watch = [k for k, p in pools.items() if 0.5 <= hours(p["detected_at"], at) <= KEEP_H]
    live = {}
    for i in range(0, len(watch), 30):
        if a.fixture:
            data, err = json.load(open(a.fixture)), None
        else:
            data, err = get_json(MULTI.format(",".join(watch[i:i + 30]))); time.sleep(3.0)
        if err: errors.append(err); continue
        live.update(parse_multi(data))
    if not errors: record(pools, live, at)  # on an API error record nothing, so "missing" always means gone
    res = {"updated_at": at, "errors": errors, "summary": summarize(pools, target), "pools": pools}
    save(a.out, res)
    print(json.dumps({k: res[k] for k in ("updated_at", "errors", "summary")}, indent=1, ensure_ascii=False))

if __name__ == "__main__": main()
