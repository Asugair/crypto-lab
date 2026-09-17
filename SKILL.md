---
name: crypto-lab
description: Run one cycle of Abdulelah's $100 paper crypto experiment (Solana meme discovery, risk gates, cost estimate, Arabic report, decision log). Use whenever asked to run the crypto lab, scan new Solana pairs, review a meme candidate, or produce the daily crypto report. Never executes or logs real or paper trades automatically.
---

# crypto-lab · operating procedure for any agent (Opus, Sonnet, Claude Code)

Read `rules.json` first. It is the only source of rules. Do not change it to fit results; propose changes in the report under "للمراجعة المشتركة".

## Truth rules (non-negotiable)
1. No data or a failed check = `unverified` = no entry recommendation. Never fill a gap with a guess.
2. A past sell is not proof we can sell now. Boosts, paid ads, trending rank are discovery signals only, never quality.
3. Every number carries a fetch time and a source URL. Snippets alone never settle a decisive news item; fetch the page.
4. Costs are `Estimate` until a real quote is recorded at session time. Never assume 0.2% covers a meme.
5. Never open, simulate, or backfill trades. Ledger rows are written only by Abdulelah in a joint session.
6. Last known balance = last row of `data/ledger.csv`. If missing, say "last known balance" and stop; never invent a current value.
7. Say plainly that sections are self-reviews, not independent agents, unless real sub-agents ran.
8. Result is "انتظار" when evidence is insufficient. Do not repeat alerts without a change.

## Cycle (in order)
1. `python3 scripts/discover.py` → `data/candidates.json` (GeckoTerminal public API, keyless, ≤30 req/min; pages ×2.2 s sleep).
2. `python3 scripts/risk.py` → `data/risk.json` (public Solana RPC `api.mainnet-beta.solana.com`; set `SOL_RPC` to another public endpoint if rate-limited).
3. `python3 scripts/cost.py --liquidity <usd> [--quote-in-pct X --quote-out-pct Y]` per surviving candidate.
4. Fill `templates/report_template.md` in Arabic. Append one line to `data/decisions.jsonl`.
5. Market/news section: search, then fetch the original source (regulator, exchange blog, Fed, CoinDesk/NPR for votes). Record event date and publish date separately.
`./run.sh` does steps 1 to 3 and writes `data/latest.json`.

## Verdicts
- `reject`: any hard gate hit (mint/freeze authority, transfer fee / permanent delegate / transfer hook / frozen default state, top-10 non-pool > 30%, single non-pool > 10%, no sells observed).
- `unverified`: a check could not run (RPC error, holder class unknown, trades page missing).
- `needs_live_verification`: passed all gates that ran. Still NOT an entry signal; a report older than one hour is stale for scalping. Requires a joint session with live exit monitoring.
- `watch`: agent judgement, must state the trigger that would upgrade or drop it.

## When the network is blocked (chat environments)
The chat sandbox cannot reach GeckoTerminal/RPC directly (`HTTP 403` from the egress proxy). Use these, in order:
A. **GitHub relay (preferred).** `.github/workflows/scan.yml` runs `run.sh` four times a day on a free GitHub account and commits `data/latest.json` + `data/history/`. Abdulelah pastes the raw URL once (`https://raw.githubusercontent.com/<user>/<repo>/main/data/latest.json`); the agent fetches it with `web_fetch` (a URL typed by the user is always fetchable). Report from that file and quote its `cycle_at`.
B. **Search-then-fetch.** `web_fetch` only opens URLs that already appeared in the conversation. Run `web_search` with the exact URL string (e.g. `api.geckoterminal.com/api/v2/networks/solana/new_pools`) so it shows up in results, then fetch it. Server-rendered fallbacks that worked on 2026-09-17: `geckoterminal.com/explore/new-crypto-pools` (all networks, minutes-old only), `dexpaprika.com/solana/pool/<pool>` (created date, token addresses). Label any page-scraped number as `page-scraped`.
C. **Dry run for logic only.** `python3 scripts/discover.py --fixture tests/fixture_new_pools.json` and `python3 scripts/risk.py --fixture tests/fixture_risk.json`. Output is fixture data, never report it as market data.
If A and B both fail: discovery = 0 scanned, status `no_data`, decision `انتظار`. That is a valid, honest report.

## Daily summary (first run 09:00 to 11:00 Riyadh)
Coverage actually achieved; scanned/excluded/candidates; biggest documented change; reject reasons; what the joint review needs; five-minute review reminder. On 2026-09-26 morning: remind to close the experiment and compute net-of-cost result from `data/ledger.csv` only. That is the last scheduled cycle; do not extend.

## What this package cannot do
Read wallets, sign, quote real slippage, detect honeypots beyond the listed gates, or see MEV/priority-fee reality. Those are joint-session tasks with the real DEX quote screen open.
