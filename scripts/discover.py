"""Discovery: new Solana pools from GeckoTerminal public API (keyless, ~30 req/min).
Usage: python scripts/discover.py [--pages 5] [--out data/candidates.json] [--fixture file.json]
Never trades. Trending/boost signals are NOT used as quality signals."""
import sys, json, time, argparse
from common import get_json, now_iso, load_rules, save, hours_since

API = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools?include=base_token,dex&page={}"

def parse_page(payload):
    inc = {i["id"]: i for i in payload.get("included", [])}
    out = []
    for p in payload.get("data", []):
        a = p["attributes"]
        rel = p.get("relationships", {})
        base_id = rel.get("base_token", {}).get("data", {}).get("id", "")
        dex_id = rel.get("dex", {}).get("data", {}).get("id", "")
        tok = inc.get(base_id, {}).get("attributes", {})
        tx1 = (a.get("transactions") or {}).get("h1", {}) or {}
        out.append({
            "pool_address": a["address"],
            "pair": a["name"],
            "token_address": base_id.replace("solana_", ""),
            "token_symbol": tok.get("symbol"),
            "dex": inc.get(dex_id, {}).get("attributes", {}).get("name", dex_id),
            "created_at": a.get("pool_created_at"),
            "liquidity_usd": float(a.get("reserve_in_usd") or 0),
            "volume_h1_usd": float((a.get("volume_usd") or {}).get("h1") or 0),
            "volume_h24_usd": float((a.get("volume_usd") or {}).get("h24") or 0),
            "txns_h1": int(tx1.get("buys", 0) or 0) + int(tx1.get("sells", 0) or 0),
            "sells_h1": int(tx1.get("sells", 0) or 0),
            "price_change_h1_pct": (a.get("price_change_percentage") or {}).get("h1"),
            "fdv_usd": a.get("fdv_usd"),
            "source_url": f"https://www.geckoterminal.com/solana/pools/{a['address']}",
        })
    return out

def apply_filters(pools, f):
    kept, excluded = [], []
    for p in pools:
        reasons = []
        if not p["created_at"]:
            reasons.append("no_created_at")
        else:
            age = hours_since(p["created_at"]); p["age_hours"] = round(age, 2)
            if age < f["age_hours_min"]: reasons.append("too_young")
            if age > f["age_hours_max"]: reasons.append("too_old")
        if p["liquidity_usd"] < f["min_liquidity_usd"]: reasons.append("low_liquidity")
        if p["volume_h1_usd"] < f["min_volume_h1_usd"]: reasons.append("low_volume_h1")
        if p["txns_h1"] < f["min_txns_h1"]: reasons.append("low_txns_h1")
        if p["sells_h1"] == 0: reasons.append("no_sells_seen_h1")
        (excluded if reasons else kept).append({**p, "exclude_reasons": reasons})
    kept.sort(key=lambda x: -x["volume_h1_usd"])
    return kept[: f["max_candidates"]], excluded

def _summ(excl):
    s = {}
    for e in excl:
        for r in e["exclude_reasons"]: s[r] = s.get(r, 0) + 1
    return s

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=5)
    ap.add_argument("--out", default="data/candidates.json")
    ap.add_argument("--fixture")
    ap.add_argument("--rules", default="rules.json")
    a = ap.parse_args()
    f = load_rules(a.rules)["discovery_filters"]
    pools, errors = [], []
    if a.fixture:
        pools = parse_page(json.load(open(a.fixture)))
    else:
        for pg in range(1, a.pages + 1):
            data, err = get_json(API.format(pg))
            if err: errors.append({"page": pg, "error": err}); break
            pools += parse_page(data); time.sleep(2.2)
    cands, excl = apply_filters(pools, f)
    res = {"fetched_at": now_iso(), "source": "GeckoTerminal public API v2 (keyless)",
           "filters": f, "scanned": len(pools), "excluded": len(excl), "candidates": len(cands),
           "errors": errors, "candidates_list": cands, "exclusion_summary": _summ(excl),
           "status": "ok" if pools and not errors else ("partial" if pools else "no_data")}
    save(a.out, res)
    print(json.dumps({k: res[k] for k in ("fetched_at","status","scanned","excluded","candidates","errors","exclusion_summary")}, indent=2))
    for c in cands:
        print(f"- {c['pair']} age={c.get('age_hours')}h liq=${c['liquidity_usd']:,.0f} vol1h=${c['volume_h1_usd']:,.0f} {c['source_url']}")

if __name__ == "__main__": main()
