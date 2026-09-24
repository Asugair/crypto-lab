"""One short Arabic page with every number the next agent or Abdulelah needs, built after each scan from the data files.
An agent reads data/brief.md (plus LESSONS.md, rules.json, MEMORY.md) instead of five JSON files: fewer tokens per cycle.
Pure formatting: no analysis, no recommendation; every section names its source file and fetch time.
Missing or broken inputs become a visible "غير متوفر" line, never a guess.
Usage: python scripts/brief.py [--data data] [--out data/brief.md]"""
import argparse, csv, json, os

def load(path):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return None

def n(x, d=1, suffix=""):
    if x is None: return "—"
    try: return f"{float(x):,.{d}f}{suffix}"
    except (TypeError, ValueError): return str(x)

def sign(x):
    return "—" if x is None else (f"+{x:.1f}%" if x >= 0 else f"{x:.1f}%")

VERDICT = {"reject": "مرفوض", "unverified": "غير متحقق", "needs_live_verification": "يحتاج تحقق حي", "watch": "مراقبة"}

def scan_section(l):
    if not l: return ["## الفحص", "غير متوفر (`data/latest.json`)."]
    ex = sorted((l.get("exclusion_summary") or {}).items(), key=lambda kv: -kv[1])
    out = ["## الفحص", f"- الدورة {l.get('cycle_at')} · الحالة {l.get('discovery_status')} · المفحوص {l.get('scanned')} · "
           f"المستبعد {l.get('excluded')} · المرشحين {len(l.get('candidates', []))}",
           "- أكثر أسباب الاستبعاد: " + "، ".join(f"{k} {v}" for k, v in ex[:5]),
           "- البيانات منتهية للمضاربة بعد 60 دقيقة من وقت الدورة."]
    if l.get("candidates"):
        out += ["", "| الزوج | الحكم | العمر س | السيولة $ | حجم الساعة ÷ السيولة | أكبر 10 مع المجمعات % | التكلفة % | فحص الحاملين |",
                "|---|---|---|---|---|---|---|---|"]
        for c in l["candidates"]:
            ratio = c["volume_h1_usd"] / c["liquidity_usd"] if c.get("liquidity_usd") else None
            out.append(f"| {c['pair']} | {VERDICT.get(c['verdict'], c['verdict'])} | {n(c.get('age_hours'))} | "
                       f"{n(c.get('liquidity_usd'), 0)} | {n(ratio, 0, '×')} | {n(c.get('gt_top10_incl_pools_pct'))} | "
                       f"{n(c.get('cost_pct_est'), 2)} | [Solscan]({c.get('manual_holder_check_url')}) |")
        errs = {e.split(":")[0] for c in l["candidates"] for e in c.get("check_errors", [])}
        if errs: out.append(f"- فحوصات فشلت: {', '.join(sorted(errs))}")
    return out

def snapshot_section(s):
    if not s: return ["## تتبّع الأسعار الحي", "غير متوفر (`data/snapshots.json`)."]
    m = s.get("summary", {})
    return ["## تتبّع الأسعار الحي", f"- آخر تحديث {s.get('updated_at')} · المتابَعين {m.get('tracked')} · "
            f"لهم قراءة حوالي يوم {m.get('with_day_observation')} · ماتوا أو جفّت سيولتهم {m.get('dead_or_drained_by_day')}",
            f"- الوسيط للكل (الميت = -100%): {sign(m.get('day_median_ret_pct_all_dead_as_minus100'))} · "
            f"فوق الهدف + التكلفة: {n(m.get('day_share_above_target_plus_cost_pct'), 0, '%')} · "
            f"نزل 50% أو مات: {n(m.get('day_share_down_50pct_or_dead'), 0, '%')}",
            "- ملاحظات أسعار، مو صفقات. قاعدة قرار 30 سبتمبر في `MEMORY.md`."]

def markets_section(mk, br):
    if not mk: return ["## البدائل", "غير متوفر (`data/markets.json`)."]
    rates = (br or {}).get("assets", {})
    out = ["## البدائل", f"- جُلبت {mk.get('fetched_at')} · السنين من `data/base_rates.json` ({(br or {}).get('fetched_at', 'غير متوفر')})", "",
           "| الأصل | السعر | من بداية التجربة | شهر | فوق متوسط 200 | العائد السنوي المركّب | أسوأ هبوط تاريخي | عمر البيانات بالسنين |",
           "|---|---|---|---|---|---|---|---|"]
    for e in mk.get("etfs", []):
        r = rates.get(e["symbol"], {})
        short = " ⚠️ قصير" if r.get("short_history") else ""
        out.append(f"| {e['symbol']} | {n(e.get('close'), 2)} | {sign(e.get('ret_since_experiment_start_pct'))} | "
                   f"{sign(e.get('ret_1m_pct'))} | {'نعم' if e.get('above_sma200') else ('لا' if e.get('above_sma200') is False else '—')} | "
                   f"{sign(r.get('cagr_pct'))} | {sign(r.get('worst_drawdown_pct'))} | {n(r.get('history_years'))}{short} |")
    b = mk.get("btc")
    if b:
        r = rates.get("BTC", {})
        out.append(f"| BTC | {n(b.get('price'), 0)} | {sign(b.get('ret_since_experiment_start_pct'))} | {sign(b.get('ret_30d_pct'))} | "
                   f"{'نعم' if (b.get('mayer_multiple') or 0) > 1 else 'لا'} | {sign(r.get('cagr_pct'))} | {sign(r.get('worst_drawdown_pct'))} | "
                   f"{n(r.get('history_years'))} |")
        fg = b.get("fear_greed") or {}
        out.append(f"- البتكوين: مضاعف ماير {n(b.get('mayer_multiple'), 2)} · RSI {n(b.get('rsi14'))} · تذبذب 30 يوم {n(b.get('vol30d_annualized_pct'), 0, '%')} · "
                   f"البعد عن قمة 300 يوم {sign(b.get('drawdown_from_300d_high_pct'))} · الخوف والطمع {fg.get('value', '—')} ({fg.get('label', '—')})")
    if any(r.get("short_history") for r in rates.values()):
        out.append("- ⚠️ قصير = أقل من 3 سنين بيانات. أداء سنة قوية وحدها ما يعتبر معدل تاريخي.")
    errs = (mk.get("errors") or []) + ((br or {}).get("errors") or [])
    if errs: out.append(f"- أخطاء جلب: {' | '.join(errs)}")
    out.append("- للمقارنة فقط، مو إشارة دخول. تصنيف الصناديق \"حلال\" حسب مُصدريها.")
    return out

def ledger_line(path):
    try:
        rows = list(csv.DictReader(open(path)))
        r = rows[-1]
        return [f"## السجل", f"- آخر رصيد موثق: {r['portfolio_after_usd']}$ ({r['ts_utc']}، {r['exit_reason'] or r['side']}). يكتبه عبدالإله فقط."]
    except Exception:
        return ["## السجل", "- آخر رصيد موثق: غير متوفر. لا نفترض رصيدًا."]

def build(data):
    l, s = load(f"{data}/latest.json"), load(f"{data}/snapshots.json")
    mk, br = load(f"{data}/markets.json"), load(f"{data}/base_rates.json")
    lines = [f"# ملخص المختبر · الدورة {(l or {}).get('cycle_at', 'غير متوفر')}",
             "مولّد آليًا من ملفات `data/` بدون تحليل ولا توصية. اقرأ `LESSONS.md` و`rules.json` و`MEMORY.md` قبل أي حكم.", ""]
    for sec in (scan_section(l), snapshot_section(s), markets_section(mk, br), ledger_line(f"{data}/ledger.csv")):
        lines += sec + [""]
    return "\n".join(lines)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data"); ap.add_argument("--out", default="data/brief.md")
    a = ap.parse_args()
    txt = build(a.data)
    open(a.out, "w").write(txt)
    print(txt)

if __name__ == "__main__": main()
