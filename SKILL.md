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
1. `python3 scripts/discover.py` → `data/candidates.json` (GeckoTerminal public API, keyless; 6 discovery sources, 3 s between requests; 429s are logged in `errors` and the status becomes `partial`).
2. `python3 scripts/risk.py` → `data/risk.json` (keyless public Solana RPCs tried in order; failures are recorded per candidate in `check_errors`).
3. `python3 scripts/cost.py --liquidity <usd> [--quote-in-pct X --quote-out-pct Y]` per surviving candidate.
4. Manual holder check (section below) for every candidate whose `missing_checks` contains `holders`.
5. Fill `templates/report_template.md` in Arabic. Append one line to `data/decisions.jsonl`.
6. Market/news section: search, then fetch the original source (regulator, exchange blog, Fed, CoinDesk/NPR for votes). Record event date and publish date separately.
`bash run.sh` does steps 1 to 3 and writes `data/latest.json`; GitHub Actions runs it on schedule.

Brand gate (added 2026-09-24): symbols/names matching `discovery_filters.reject_brand_impersonation` are excluded at discovery as `brand_impersonation`.

## Verdicts
- `reject`: any hard gate hit (mint/freeze authority, transfer fee / permanent delegate / transfer hook / frozen default state, top-10 non-pool > 30%, single non-pool > 10%, no sells observed).
- `unverified`: a check could not run (RPC error, holder class unknown, trades page missing).
- `needs_live_verification`: passed all gates that ran. Still NOT an entry signal; a report older than one hour is stale for scalping. Requires a joint session with live exit monitoring.
- `watch`: agent judgement, must state the trigger that would upgrade or drop it.

## When the network is blocked (chat environments)
The chat sandbox cannot reach GeckoTerminal/RPC directly (`HTTP 403` from the egress proxy). Use these, in order:
A. **GitHub relay (preferred).** `.github/workflows/scan.yml` runs `run.sh` four times a day and commits `data/latest.json` + `data/history/`. Abdulelah pastes the raw URL once (`https://raw.githubusercontent.com/Asugair/crypto-lab/main/data/latest.json`); the agent fetches it with `web_fetch` (a URL typed by the user is always fetchable). Report from that file and quote its `cycle_at`. `data/candidates.json` and `data/risk.json` hold the full detail.
B. **Search-then-fetch.** `web_fetch` only opens URLs that already appeared in the conversation. Run `web_search` with the exact URL string so it shows up in results, then fetch it. Server-rendered fallbacks that worked on 2026-09-17: `geckoterminal.com/explore/new-crypto-pools` (all networks, minutes-old only), `dexpaprika.com/solana/pool/<pool>` (created date, token addresses). Label any page-scraped number as `page-scraped`.
C. **Dry run for logic only.** `bash tests/run_tests.sh` (renders `tests/fixture_new_pools.template.json` with fresh timestamps). Output is fixture data, never report it as market data.
If A and B both fail: discovery = 0 scanned, status `no_data`, decision `انتظار`. That is a valid, honest report.

## Holder check: manual, by the agent, every cycle (no keys, by decision on 2026-09-17)
Public keyless RPCs answer `getTokenLargestAccounts` with HTTP 429 from GitHub Actions, so `risk.py` leaves `holders` in `missing_checks` and the verdict is `unverified`. The agent completes this check by hand for every candidate, every cycle:
1. Open `https://solscan.io/token/<token_address>#holders` (chat env: `web_search` the exact URL first, then `web_fetch`; alternatively the GeckoTerminal pool page from `source_url`).
2. Record fetch time, top-10 holders with %, and classify each: pool/program (Raydium, PumpSwap, Meteora vaults, burn address) vs wallet vs unknown.
3. Apply `rules.json` gates: top-10 non-pool > 30% or single non-pool > 10% → `reject`; any `unknown` → stays `unverified`.
4. Write the numbers into the report as `page-scraped <time>`. If the page cannot be fetched, the candidate stays `unverified`; do not estimate.
Only after this manual step may a verdict move from `unverified` to `needs_live_verification`. Never skip it and never upgrade on the strength of the automated fields alone.

## Daily summary (first run 09:00 to 11:00 Riyadh)
Coverage actually achieved; scanned/excluded/candidates; biggest documented change; reject reasons; what the joint review needs; five-minute review reminder. On 2026-09-30 morning (extended from 09-26 on 2026-09-24, see rules.json): remind to close the experiment and compute net-of-cost result from `data/ledger.csv` only. That is the last scheduled cycle; do not extend.

## What this package cannot do
Read wallets, sign, quote real slippage, detect honeypots beyond the listed gates, or see MEV/priority-fee reality. Those are joint-session tasks with the real DEX quote screen open.
