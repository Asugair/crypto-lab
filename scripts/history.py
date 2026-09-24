"""Multi-year base rates for the benchmarks: calendar-year return and max drawdown, plus full-period CAGR and worst
drawdown, for Bitcoin (Coinbase daily since 2015) and the halal ETFs in rules.json (full Stooq/Yahoo history).
This is the "what happened in past years" side of the lab memory; the live side is data/snapshots.json.
Refreshed at most once a week (history does not change). Keyless public data only.
Usage: python scripts/history.py [--out data/base_rates.json] [--rules rules.json] [--force] [--fixture f.json]"""
import argparse, csv, io, json, os, time
from datetime import datetime, timedelta, timezone
from common import get_json, now_iso, load_rules, save, hours_since
from markets import get_text, STOOQ, YAHOO

COINBASE = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400&start={}&end={}"

def btc_history():
    out, end, errs = {}, datetime.now(timezone.utc), []
    first = datetime(2015, 7, 20, tzinfo=timezone.utc)
    while end > first:
        start = max(first, end - timedelta(days=299))
        rows, err = get_json(COINBASE.format(start.strftime("%Y-%m-%dT00:00:00Z"), end.strftime("%Y-%m-%dT00:00:00Z")))
        if err: errs.append(err); break
        for c in rows or []:
            out[datetime.fromtimestamp(c[0], timezone.utc).strftime("%Y-%m-%d")] = float(c[4])
        end = start - timedelta(days=1); time.sleep(0.5)
    return sorted(out.items()), errs

def etf_history(sym):
    txt, err = get_text(STOOQ.format(sym.lower()))
    if txt and txt.startswith("Date"):
        rows = [r for r in csv.DictReader(io.StringIO(txt)) if r.get("Close") not in (None, "", "N/D")]
        if rows: return [(r["Date"], float(r["Close"])) for r in rows], "stooq", None
    d, err2 = get_json(YAHOO.format(sym).replace("range=1y", "range=max"))
    try:
        r = d["chart"]["result"][0]
        s = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c)
             for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        return s, "yahoo", None
    except Exception:
        return None, None, f"stooq: {err or 'no csv'} | yahoo: {err2 or 'bad payload'}"

def max_dd(closes):
    peak, worst = closes[0], 0.0
    for c in closes:
        peak = max(peak, c); worst = min(worst, c / peak - 1)
    return round(100 * worst, 1)

def stats(series):
    """series = [(YYYY-MM-DD, close)] oldest first."""
    years = {}
    for d, c in series: years.setdefault(d[:4], []).append(c)
    ys, prev = [], None
    for y in sorted(years):
        cl = years[y]; base = prev if prev else cl[0]
        ys.append({"year": y, "ret_pct": round(100 * (cl[-1] / base - 1), 1), "max_dd_pct": max_dd([base] + cl),
                   "partial": prev is None or y == series[-1][0][:4]})
        prev = cl[-1]
    closes = [c for _, c in series]
    yrs = (datetime.strptime(series[-1][0], "%Y-%m-%d") - datetime.strptime(series[0][0], "%Y-%m-%d")).days / 365.25
    full = [y for y in ys if not y["partial"]]
    # under 3 years (e.g. SPTE) one good run is not a base rate: flag it so reports do not read it as one
    return {"from": series[0][0], "to": series[-1][0], "years": ys, "history_years": round(yrs, 1),
            "short_history": yrs < 3, "since_inception_ret_pct": round(100 * (closes[-1] / closes[0] - 1), 1),
            "cagr_pct": round(100 * ((closes[-1] / closes[0]) ** (1 / yrs) - 1), 1) if yrs >= 1 else None,
            "worst_drawdown_pct": max_dd(closes),
            "full_years": len(full), "share_full_years_up_pct": round(100 * sum(y["ret_pct"] > 0 for y in full) / len(full)) if full else None}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/base_rates.json"); ap.add_argument("--rules", default="rules.json")
    ap.add_argument("--force", action="store_true"); ap.add_argument("--fixture")
    a = ap.parse_args()
    if not a.force and not a.fixture and os.path.exists(a.out):
        if hours_since(json.load(open(a.out))["fetched_at"]) < 24 * 7:
            print("base rates fresh (< 7 days), skipped"); return
    fx = json.load(open(a.fixture)) if a.fixture else None
    res, errors = {"fetched_at": now_iso(), "assets": {}}, []
    series, errs = ([tuple(x) for x in fx["BTC"]], []) if fx else btc_history()
    errors += [f"BTC: {e}" for e in errs]
    if series: res["assets"]["BTC"] = {"source": "coinbase daily", **stats(series)}
    for sym in load_rules(a.rules)["benchmarks"]["halal_etfs"]:
        s, src, err = ([tuple(x) for x in fx[sym]], "fixture", None) if fx else etf_history(sym)
        if err or not s: errors.append(f"{sym}: {err}"); continue
        res["assets"][sym] = {"source": src, **stats(s)}
    res["errors"] = errors
    res["caveat"] = "Price returns only (ETF dividends and fees excluded). First and current years are partial. Past years are not a forecast."
    save(a.out, res)
    print(json.dumps({k: {kk: v[kk] for kk in ("from", "to", "cagr_pct", "worst_drawdown_pct", "share_full_years_up_pct")}
                      for k, v in res["assets"].items()}, indent=1), errors)

if __name__ == "__main__": main()
