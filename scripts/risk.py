"""Risk review of candidates via public Solana RPC (no key) + GeckoTerminal trades.
Checks: mint/freeze authority, token program (SPL vs Token-2022), dangerous extensions,
top-20 holder concentration with pool/program-owned accounts separated, recent sells seen.
Any check that fails to run => verdict 'unverified'. A past sell is NOT proof we can sell now.
Usage: python scripts/risk.py [--in data/candidates.json] [--out data/risk.json] [--fixture dir]"""
import json, argparse, os, time
from common import post_json, get_json, now_iso, load_rules, save

RPC = os.environ.get("SOL_RPC", "https://api.mainnet-beta.solana.com")
SYSTEM_PROGRAM = "11111111111111111111111111111111"
TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
TRADES = "https://api.geckoterminal.com/api/v2/networks/solana/pools/{}/trades"

def rpc(method, params, fixture=None):
    if fixture is not None:
        return fixture, None
    r, err = post_json(RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if err: return None, err
    if "error" in r: return None, str(r["error"])
    return r.get("result"), None

def parse_mint(acc):
    """acc = result of getAccountInfo(jsonParsed). Returns dict of mint facts."""
    v = (acc or {}).get("value")
    if not v: return {"error": "mint_not_found"}
    owner = v.get("owner"); parsed = (v.get("data") or {}).get("parsed") or {}
    info = parsed.get("info", {})
    ext = [e.get("extension") for e in info.get("extensions", [])] if isinstance(info.get("extensions"), list) else []
    ext_details = {e.get("extension"): e.get("state") for e in info.get("extensions", [])} if ext else {}
    return {
        "program": "token2022" if owner == TOKEN_2022 else ("spl_token" if owner else "unknown"),
        "mint_authority": info.get("mintAuthority"),
        "freeze_authority": info.get("freezeAuthority"),
        "supply_raw": int(info.get("supply", 0) or 0),
        "decimals": info.get("decimals"),
        "extensions": ext, "extension_details": ext_details,
    }

def holder_concentration(largest, owners_info, pool_addrs, supply):
    """largest = getTokenLargestAccounts result['value']; owners_info = {token_account: (owner_wallet, owner_wallet_program_owner)}"""
    rows, nonpool = [], []
    for h in largest:
        amt = int(h.get("amount", 0) or 0); pct = 100 * amt / supply if supply else None
        wallet, wallet_owner = owners_info.get(h["address"], (None, None))
        is_pool = (wallet in pool_addrs) or (wallet_owner not in (None, SYSTEM_PROGRAM))
        rows.append({"token_account": h["address"], "owner": wallet, "pct": round(pct, 2) if pct is not None else None,
                     "class": "pool_or_program" if is_pool else ("wallet" if wallet_owner == SYSTEM_PROGRAM else "unknown")})
        if not is_pool: nonpool.append(pct or 0)
    nonpool.sort(reverse=True)
    return {"top20": rows, "top10_nonpool_pct": round(sum(nonpool[:10]), 2), "max_single_nonpool_pct": round(nonpool[0], 2) if nonpool else 0.0}

def verdict(mint, conc, sells_recent, g):
    reasons, missing = [], []
    if "error" in mint: missing.append("mint")
    else:
        if g["reject_if_mint_authority"] and mint["mint_authority"]: reasons.append("mint_authority_present")
        if g["reject_if_freeze_authority"] and mint["freeze_authority"]: reasons.append("freeze_authority_present")
        for e in mint["extensions"]:
            if e in g["reject_extensions"]: reasons.append(f"extension_{e}")
        st = (mint.get("extension_details") or {}).get("defaultAccountState", {})
        if isinstance(st, dict) and st.get("accountState") == "frozen": reasons.append("extension_defaultAccountState_frozen")
    if conc is None: missing.append("holders")
    else:
        if conc["top10_nonpool_pct"] > g["max_top10_nonpool_pct"]: reasons.append(f"top10_nonpool_{conc['top10_nonpool_pct']}pct")
        if conc["max_single_nonpool_pct"] > g["max_single_nonpool_pct"]: reasons.append(f"single_nonpool_{conc['max_single_nonpool_pct']}pct")
        if any(r["class"] == "unknown" for r in conc["top20"]): missing.append("holder_class_unknown")
    if sells_recent is None: missing.append("trades")
    elif sells_recent == 0: reasons.append("no_recent_sells_observed")
    if reasons: return "reject", reasons, missing
    if missing and g["unverified_if_any_check_missing"]: return "unverified", reasons, missing
    return "needs_live_verification", reasons, missing

def review(c, g, fixture=None):
    fx = lambda k: (fixture or {}).get(k)
    mint_acc, e1 = rpc("getAccountInfo", [c["token_address"], {"encoding": "jsonParsed"}], fx("mint"))
    mint = parse_mint(mint_acc) if not e1 else {"error": e1}
    conc = None
    largest, e2 = rpc("getTokenLargestAccounts", [c["token_address"]], fx("largest"))
    if not e2 and largest and "error" not in mint:
        owners = {}
        for h in largest.get("value", [])[:20]:
            ta, e3 = rpc("getAccountInfo", [h["address"], {"encoding": "jsonParsed"}], (fx("accounts") or {}).get(h["address"]))
            wallet = None; wo = None
            if not e3 and ta and ta.get("value"):
                wallet = (((ta["value"].get("data") or {}).get("parsed") or {}).get("info") or {}).get("owner")
                if wallet:
                    wa, e4 = rpc("getAccountInfo", [wallet, {"encoding": "base64"}], (fx("wallets") or {}).get(wallet))
                    if not e4 and wa and wa.get("value"): wo = wa["value"].get("owner")
                    elif not e4 and wa is not None and wa.get("value") is None: wo = SYSTEM_PROGRAM  # empty wallet = plain account
            owners[h["address"]] = (wallet, wo)
            if fixture is None: time.sleep(0.15)
        conc = holder_concentration(largest.get("value", []), owners, {c["pool_address"]}, mint["supply_raw"])
    sells_recent = None
    tr, e5 = (fx("trades"), None) if fixture else get_json(TRADES.format(c["pool_address"]))
    if not e5 and tr:
        sells_recent = sum(1 for t in tr.get("data", []) if t["attributes"].get("kind") == "sell")
    v, reasons, missing = verdict(mint, conc, sells_recent, g)
    return {**{k: c[k] for k in ("pair","token_address","pool_address","source_url")},
            "checked_at": now_iso(), "rpc": RPC if not fixture else "fixture", "mint": mint,
            "holders": conc, "sells_in_last_trades_page": sells_recent,
            "verdict": v, "reject_reasons": reasons, "missing_checks": missing,
            "caveat": "Past sells do not prove we can sell now. Costs/slippage not included here; run cost.py."}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="data/candidates.json")
    ap.add_argument("--out", default="data/risk.json")
    ap.add_argument("--fixture"); ap.add_argument("--rules", default="rules.json")
    a = ap.parse_args()
    g = load_rules(a.rules)["risk_gates"]
    cands = json.load(open(a.inp))["candidates_list"]
    fixture = json.load(open(a.fixture)) if a.fixture else None
    out = [review(c, g, (fixture or {}).get(c["token_address"]) if fixture else None) for c in cands]
    save(a.out, {"checked_at": now_iso(), "reviews": out})
    for r in out:
        print(f"{r['pair']}: {r['verdict'].upper()} reasons={r['reject_reasons']} missing={r['missing_checks']}")
    if not out: print("no candidates to review")

if __name__ == "__main__": main()
