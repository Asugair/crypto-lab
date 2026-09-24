"""Benchmarks next to the meme lab: Shariah-screened US ETFs and Bitcoin indicators. Keyless public data only.
Context for the joint review and the 2026-09-30 decision ("memes vs a plain alternative"), never an entry signal.
The ETFs are the ones their issuers market as Shariah-compliant (each has its own Shariah board); that label is the
issuer's claim, not a ruling by this lab.
Usage: python scripts/markets.py [--out data/markets.json] [--rules rules.json] [--fixture f.json]"""
import argparse, csv, io, json, math, time, urllib.request
from datetime import datetime, timezone
from common import UA, get_json, now_iso, load_rules, save

STOOQ = "https://stooq.com/q/d/l/?s={}.us&i=d"
YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1y&interval=1d"
COINBASE = "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=86400"  # up to 300 daily candles
FNG = "https://api.alternative.me/fng/?limit=1"

def get_text(url, timeout=20):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
            return r.read().decode(), None
    except Exception as e:
        return None, str(e)

def sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None

def rsi(xs, n=14):
    """Wilder's RSI on closes, oldest first."""
    if len(xs) <= n: return None
    d = [b - a for a, b in zip(xs, xs[1:])]
    up = sum(max(x, 0) for x in d[:n]) / n; dn = sum(max(-x, 0) for x in d[:n]) / n
    for x in d[n:]:
        up = (up * (n - 1) + max(x, 0)) / n; dn = (dn * (n - 1) + max(-x, 0)) / n
    return 100.0 if dn == 0 else round(100 - 100 / (1 + up / dn), 1)

def pct(a, b):
    return round(100 * (b / a - 1), 2) if a and b else None

def since(series, day):
    """Close on the last trading day before `day` -> latest close (the experiment started on `day` morning)."""
    before = [c for d, c in series if d < day]
    return pct(before[-1], series[-1][1]) if before else None

def etf_series(sym):
    txt, err = get_text(STOOQ.format(sym.lower()))
    if txt and txt.startswith("Date"):
        rows = [r for r in csv.DictReader(io.StringIO(txt)) if r.get("Close") not in (None, "", "N/D")]
        if rows: return [(r["Date"], float(r["Close"])) for r in rows][-300:], "stooq", None
    d, err2 = get_json(YAHOO.format(sym))
    try:
        r = d["chart"]["result"][0]; closes = r["indicators"]["quote"][0]["close"]
        s = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(r["timestamp"], closes) if c]
        return s, "yahoo", None
    except Exception:
        return None, None, f"stooq: {err or 'no csv'} | yahoo: {err2 or 'bad payload'}"

def etf_row(sym, series, source, start):
    closes = [c for _, c in series]
    return {"symbol": sym, "source": source, "last_date": series[-1][0], "close": round(closes[-1], 2),
            "ret_since_experiment_start_pct": since(series, start), "ret_1m_pct": pct(closes[-22], closes[-1]) if len(closes) > 22 else None,
            "sma50": round(sma(closes, 50), 2) if sma(closes, 50) else None,
            "sma200": round(sma(closes, 200), 2) if sma(closes, 200) else None,
            "above_sma200": closes[-1] > sma(closes, 200) if sma(closes, 200) else None}

def btc_row(candles, fng, start):
    # Coinbase rows: [time, low, high, open, close, volume], newest first
    s = sorted((datetime.fromtimestamp(c[0], timezone.utc).strftime("%Y-%m-%d"), float(c[4])) for c in candles)
    closes = [c for _, c in s]
    rets = [math.log(b / a) for a, b in zip(closes[-31:], closes[-30:])]
    vol = round(100 * statistics_stdev(rets) * math.sqrt(365), 1) if len(rets) > 2 else None
    s200 = sma(closes, 200)
    return {"source": "coinbase daily", "last_date": s[-1][0], "price": round(closes[-1], 0),
            "ret_since_experiment_start_pct": since(s, start), "ret_7d_pct": pct(closes[-8], closes[-1]) if len(closes) > 8 else None,
            "ret_30d_pct": pct(closes[-31], closes[-1]) if len(closes) > 31 else None,
            "sma50": round(sma(closes, 50), 0) if sma(closes, 50) else None, "sma200": round(s200, 0) if s200 else None,
            "mayer_multiple": round(closes[-1] / s200, 2) if s200 else None, "rsi14": rsi(closes),
            "vol30d_annualized_pct": vol, "drawdown_from_300d_high_pct": pct(max(closes), closes[-1]),
            "fear_greed": fng}

def statistics_stdev(xs):
    m = sum(xs) / len(xs); return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/markets.json"); ap.add_argument("--rules", default="rules.json"); ap.add_argument("--fixture")
    a = ap.parse_args()
    r = load_rules(a.rules); b = r["benchmarks"]; start = r["experiment"]["start_date"]
    fx = json.load(open(a.fixture)) if a.fixture else None
    out, errors = {"fetched_at": now_iso(), "etfs": [], "btc": None}, []
    for sym in b["halal_etfs"]:
        series, src, err = (fx["etfs"][sym], "fixture", None) if fx else etf_series(sym)
        if err or not series: errors.append(f"{sym}: {err}"); continue
        out["etfs"].append(etf_row(sym, series, src, start)); time.sleep(0 if fx else 1)
    candles, err = (fx["btc"], None) if fx else get_json(COINBASE)
    if err or not candles: errors.append(f"btc: {err}")
    else:
        f, ferr = (fx.get("fng"), None) if fx else get_json(FNG)
        fng = {"value": int(f["data"][0]["value"]), "label": f["data"][0]["value_classification"]} if f and not ferr else {"error": ferr}
        out["btc"] = btc_row(candles, fng, start)
    out["errors"] = errors
    out["caveat"] = ("Context, not signals. Shariah status is each issuer's claim. Returns are price only, "
                     "before fees/spreads; 'since experiment start' uses the last close before " + start + ".")
    save(a.out, out)
    print(json.dumps(out, indent=1, ensure_ascii=False))

if __name__ == "__main__": main()
