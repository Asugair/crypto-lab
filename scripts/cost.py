"""Round-trip cost estimate for one $10 meme position. All outputs labelled Estimate
until replaced by a real quote (Jupiter quote screen / DEX UI) recorded at session time.
Usage: python scripts/cost.py --liquidity 25000 [--sol-price 98] [--position 10] [--quote-in-pct X --quote-out-pct Y]"""
import argparse, json
from common import load_rules

def impact_pct(amount_usd, liquidity_usd):
    # constant product, one side of pool ~ liquidity/2 ; impact ~ amount / (side + amount)
    side = liquidity_usd / 2
    return 100 * amount_usd / (side + amount_usd) if side > 0 else 100.0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--liquidity", type=float, required=True)
    ap.add_argument("--position", type=float)
    ap.add_argument("--sol-price", type=float, default=100.0)
    ap.add_argument("--quote-in-pct", type=float, help="real quoted price impact on buy, if you have it")
    ap.add_argument("--quote-out-pct", type=float, help="real quoted price impact on sell, if you have it")
    ap.add_argument("--rules", default="rules.json")
    a = ap.parse_args()
    r = load_rules(a.rules); s = r["session_rules"]; ca = r["cost_assumptions_estimate"]
    pos = a.position or s["position_size_usd"]
    net_fee = 2 * ca["sol_network_fee_sol"] * a.sol_price
    dex = 2 * ca["dex_fee_pct"]; agg = 2 * ca["aggregator_fee_pct"]
    if a.quote_in_pct is not None and a.quote_out_pct is not None:
        slip = a.quote_in_pct + a.quote_out_pct; label = "Measured quote"
    else:
        slip = 2 * impact_pct(pos, a.liquidity); label = "Estimate (constant-product model)"
    total_pct = dex + agg + slip + 100 * net_fee / pos
    needed = s["target_net_pct"] + total_pct
    out = {"label": label, "position_usd": pos, "liquidity_usd": a.liquidity,
           "network_fee_usd_roundtrip": round(net_fee, 4), "dex_fee_pct_roundtrip": dex,
           "slippage_pct_roundtrip": round(slip, 2), "total_cost_pct_roundtrip": round(total_pct, 2),
           "gross_move_needed_for_target_pct": round(needed, 2),
           "verdict": "cost_too_high" if total_pct > s["target_net_pct"] else "cost_acceptable_if_measured"}
    print(json.dumps(out, indent=2))

if __name__ == "__main__": main()
