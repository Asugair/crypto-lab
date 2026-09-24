"""Offline tests for snapshot.py, markets.py and the Helius key handling in risk.py. Run from scripts/."""
import json, os, subprocess, tempfile
from datetime import datetime, timedelta, timezone
import sys; sys.path.insert(0, os.getcwd())

iso = lambda t: t.strftime("%Y-%m-%dT%H:%M:%SZ")
now = datetime.now(timezone.utc)
d = tempfile.mkdtemp()

# --- snapshot: detection price from the scan, later price from /pools/multi, dead pools count as misses
import snapshot
pools = {}
cand = lambda pool, price, liq: {"pair": f"{pool} / SOL", "pool_address": pool, "token_address": "M" + pool, "price_usd": price,
                                 "liquidity_usd": liq, "cost_pct_est": 0.66, "verdict": "unverified"}
snapshot.add_new(pools, {"cycle_at": iso(now - timedelta(hours=24)),
                         "candidates": [cand("UP", 1.0, 50000), cand("DOWN", 1.0, 50000), cand("DRAIN", 1.0, 50000),
                                        cand("GONE", 1.0, 50000), {**cand("NOPRICE", None, 1), "price_usd": None}]})
assert set(pools) == {"UP", "DOWN", "DRAIN", "GONE"}, pools  # no price at discovery = cannot be tracked honestly
live = {"UP": {"price": 1.5, "liquidity_usd": 60000, "volume_h1_usd": 1},
        "DOWN": {"price": 0.4, "liquidity_usd": 30000, "volume_h1_usd": 1},
        "DRAIN": {"price": 2.0, "liquidity_usd": 500, "volume_h1_usd": 0}}
snapshot.record(pools, live, iso(now))
assert pools["UP"]["obs"][0]["ret_pct"] == 50.0 and pools["GONE"]["obs"][0]["missing"], pools
s = snapshot.summarize(pools, 5)
assert s["with_day_observation"] == 4 and s["dead_or_drained_by_day"] == 2, s
assert s["day_share_above_target_plus_cost_pct"] == 25, s        # only UP beats 5% + cost, out of all 4
assert s["day_share_down_50pct_or_dead"] == 75, s                # DOWN (-60%) + DRAIN + GONE
assert s["day_median_ret_pct_all_dead_as_minus100"] == -80.0, s   # [50, -60, -100, -100]
# end-to-end with a fixture: parse /pools/multi and write the file
json.dump({"cycle_at": iso(now), "candidates": []}, open(f"{d}/latest.json", "w"))
json.dump({"pools": pools}, open(f"{d}/snap.json", "w"))
json.dump({"data": [{"attributes": {"address": "UP", "base_token_price_usd": "1.2", "reserve_in_usd": "40000",
                                    "volume_usd": {"h1": "10"}}}]}, open(f"{d}/multi.json", "w"))
subprocess.run(["python3", "snapshot.py", "--latest", f"{d}/latest.json", "--out", f"{d}/snap.json", "--rules", "../rules.json",
                "--fixture", f"{d}/multi.json"], check=True, capture_output=True)
up = json.load(open(f"{d}/snap.json"))["pools"]["UP"]["obs"]
assert len(up) == 2 and up[-1]["ret_pct"] == 20.0, up

# --- markets: indicator math and a fixture run
import markets
assert markets.sma([1, 2, 3, 4], 2) == 3.5 and markets.sma([1], 2) is None
assert markets.rsi(list(range(1, 30))) == 100.0 and markets.rsi([5] * 10) is None
assert 40 < markets.rsi([10, 11] * 20) < 60                       # alternating = balanced
series = [(iso(now - timedelta(days=300 - i))[:10], 100 + i) for i in range(300)]
start = json.load(open("../rules.json"))["experiment"]["start_date"]
row = markets.etf_row("SPUS", series, "fixture", start)
assert row["close"] == 399 and row["above_sma200"] is True and row["ret_since_experiment_start_pct"] is not None, row
candles = [[int((now - timedelta(days=i)).timestamp()), 0, 0, 0, 50000 + 100 * (299 - i), 0] for i in range(300)]
btc = markets.btc_row(candles, {"value": 50, "label": "Neutral"}, start)
assert btc["price"] == 79900 and btc["mayer_multiple"] > 1 and btc["drawdown_from_300d_high_pct"] == 0.0, btc
ETFS = json.load(open("../rules.json"))["benchmarks"]["halal_etfs"]
json.dump({"etfs": {s: series for s in ETFS}, "btc": candles,
           "fng": {"data": [{"value": "60", "value_classification": "Greed"}]}}, open(f"{d}/mk.json", "w"))
subprocess.run(["python3", "markets.py", "--out", f"{d}/m.json", "--rules", "../rules.json", "--fixture", f"{d}/mk.json"],
               check=True, capture_output=True)
m = json.load(open(f"{d}/m.json"))
assert len(m["etfs"]) == len(ETFS) and m["btc"]["fear_greed"]["value"] == 60 and not m["errors"], m

# --- risk: a Helius key goes first and never appears in what gets committed
os.environ["HELIUS_API_KEY"] = "SECRETKEY123"
import importlib, risk
importlib.reload(risk)
assert risk.RPCS[0].startswith("https://mainnet.helius-rpc.com") and risk.record_host(risk.RPCS[0]) == "mainnet.helius-rpc.com"
risk.post_json = lambda url, payload, timeout=20: (None, "HTTP 401 bad key " + url)
_, err = risk.rpc("getTokenLargestAccounts", ["x"], retries=1)
assert "SECRETKEY123" not in err and "mainnet.helius-rpc.com" in err, err
print("snapshot + markets + helius tests ok")

# --- history: calendar-year returns and drawdowns
import history
s = [("2020-06-01", 100.0), ("2020-12-31", 200.0), ("2021-03-01", 100.0), ("2021-12-31", 300.0), ("2022-12-30", 150.0), ("2023-02-01", 165.0)]
h = history.stats(s)
y = {r["year"]: r for r in h["years"]}
assert y["2020"]["ret_pct"] == 100.0 and y["2020"]["partial"] and y["2023"]["partial"], y
assert y["2021"]["ret_pct"] == 50.0 and y["2021"]["max_dd_pct"] == -50.0 and not y["2021"]["partial"], y
assert y["2022"]["ret_pct"] == -50.0 and h["full_years"] == 2 and h["share_full_years_up_pct"] == 50, h
assert h["worst_drawdown_pct"] == -50.0 and h["cagr_pct"] is not None, h
fx = {"BTC": s, **{e: s for e in ETFS}}
json.dump(fx, open(f"{d}/hist.json", "w"))
subprocess.run(["python3", "history.py", "--out", f"{d}/b.json", "--rules", "../rules.json", "--fixture", f"{d}/hist.json"],
               check=True, capture_output=True)
assert set(json.load(open(f"{d}/b.json"))["assets"]) == {"BTC", *ETFS}
print("history tests ok")
