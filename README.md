# visibility

Ship it where builders look: get your MCP server, agent plugin, skill, SDK or API listed in the registries, marketplaces and package indexes developers and agents actually search. It finds what a project can list today, builds the one asset that unlocks more listings, and finds the channels that pay. Five Agent Skills for Claude Code.

| Skill | Use it to |
|---|---|
| `/visibility:plan [path ...] [--portfolio]` | Detect listable assets (MCP server, Agent Skill, Claude plugin, OpenAPI, npm/PyPI/Rust/Swift/Go package, browser/VS Code/JetBrains/Raycast/Obsidian extension, GitHub Action, llms.txt, iOS app), ask for the ones files cannot prove (remote MCP URL, OAuth, public API, domain, Hugging Face model or dataset, test account), and rank where it can be listed now by how much traffic each listing site gets and which one asset unlocks the most listings. |
| `/visibility:register <platform-id>` | Walk one platform end to end: re-check the live submission page, build the artifacts, run publish commands after an explicit yes, hand account/payment/DNS/form steps to you, verify the listing and update the ledger. |
| `/visibility:build [asset-id \| platform-id]` | Build the missing asset that unlocks the most listings (remote MCP server, server.json, one-job browser extension, API-wrapper CLI, OpenAPI file, llms.txt docs, VS Code or Raycast extension) or a platform's own integration (Zapier app, n8n node, Make app, Notion connection, Linear app, ChatGPT app), from a recipe sourced from the platform's docs. |
| `/visibility:factory [init \| plan \| run \| report]` | Run all of the above across every repo you own from one private control folder: one ledger, a weekly queue split into what Claude prepares, what needs your yes and what only you can do (grouped by platform, so one sign-in covers every repo), and a report of which listings send traffic. |
| `/visibility:monetize [path] [--channel id]` | Rank the channels that pay (pay-per-call with x402, paid MCP marketplaces, sponsorships, paid API plans, marketplace actors, paid plugins, cloud marketplaces, merchant-of-record stores) by fit, fee and effort, and set one up. |

All are user-invoked. Nothing is published, paid for or submitted without you.

## Where each fact lives

| Fact | Home |
|---|---|
| Platforms: requirements, cost, review, link type, traffic, steps, verified flag | `skills/plan/catalog.json` |
| Monetization channels and their revenue terms | `skills/plan/catalog.json` rows with `category: "monetize"` |
| How to build an asset or a platform's integration | `skills/build/recipes/<id>.md` |
| Pricing, packaging, paywalls | `marketingskills:pricing`, `paywalls`, `offers` (not duplicated here) |
| Asset vocabulary and detection | `skills/plan/scripts/scan.py` (`ASSETS`, `detect`) |
| Developer launch channels (Show HN, Product Hunt Developer Tools) | `skills/plan/catalog.json` rows with `category: "launch"` |
| Launch strategy and timing beyond those two rows | `marketingskills:launch` (not duplicated here) |
| Generic launch/AI/SaaS directories, backlink verification, tracker format | `marketingskills:directory-submissions` (not duplicated here) |
| What an agent may do in the factory, and the `next` / `done` loop | `skills/factory/RUNBOOK.md` |
| Portfolio state: repos, priorities, ledger, metrics, reports | the control folder (`portfolio.json`, `LEDGER.csv`, `QUEUE.md`, `METRICS.csv`, `reports/`), described in `skills/factory/SKILL.md` |
| Per-project state | `<project>/.visibility/` (PRODUCT.md, SCAN.md, PLAN.md, MONETIZE.md, LEDGER.csv; git-ignored) |

Catalog rows marked `verified: no` come from secondhand sources; `register` re-checks the live page before using one. `verified: flow` means the submission flow was checked but the link the listing gives was not; `yes` means both were observed. Rows rank by `traffic`: the Tranco top-1M rank (including subdomains) of the host the listing lives on, a research ranking built from Chrome UX Report, Cloudflare Radar and other traffic data. It measures the whole site, not the one listing page. A host outside the top million gets little traffic; a row with no host to measure (in-app only, a page inside GitHub, a payment rail) ranks after the measured ones. DR figures are as claimed by the source and are no longer used for ranking. `.github/linkcheck.py` reports `submit` URLs that no longer resolve and runs weekly.

## Install

```bash
claude plugin marketplace add OrenSegal/visibility
claude plugin install visibility@visibility
```

Locally: `claude plugin marketplace add ~/Documents/GitHub/visibility`.

Gemini CLI: `gemini extensions install https://github.com/OrenSegal/visibility`. Other agents: `npx skills add OrenSegal/visibility`.

## Extend

Add a platform: one object in `catalog.json`, using asset ids from `ASSETS`; add an asset: one `ASSETS` entry and, if a file can prove it, one branch in `detect`. Add a paying channel: a catalog row with `category: "monetize"` and a `revenue` line. Add a recipe: `skills/build/recipes/<asset-or-platform-id>.md` with a `source` URL and load date. Then run the checks in `AGENTS.md`.
