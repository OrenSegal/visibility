# visibility

Get a product listed on high-authority agent, integration, extension and API marketplaces (a dedicated page, an install button, often a backlink), build the one asset that unlocks more of them, and find the channels that pay. Four Agent Skills for Claude Code.

| Skill | Use it to |
|---|---|
| `/visibility:plan [path ...] [--portfolio]` | Detect listable assets (MCP server, Agent Skill, Claude plugin, OpenAPI, npm CLI, browser/VS Code/Raycast/Obsidian extension, GitHub Action, llms.txt, iOS app), ask for the ones files cannot prove (remote MCP URL, OAuth, public API, domain, test account), and rank where it can be listed now and which one asset unlocks the most listings. |
| `/visibility:register <platform-id>` | Walk one platform end to end: re-check the live submission page, build the artifacts, run publish commands after an explicit yes, hand account/payment/DNS/form steps to you, verify the listing and update the ledger. |
| `/visibility:build [asset-id \| platform-id]` | Build the missing asset that unlocks the most listings (remote MCP server, server.json, one-job browser extension, API-wrapper CLI, OpenAPI file, llms.txt docs) or a platform's own integration (n8n node, Make app, Notion connection), from a recipe sourced from the platform's docs. |
| `/visibility:monetize [path] [--channel id]` | Rank the channels that pay (paid API plans, marketplace actors, cloud marketplaces, sponsorships, merchant-of-record stores, paid plugins, pay-per-call) by fit, fee and effort, and set one up. |

All are user-invoked. Nothing is published, paid for or submitted without you.

## Where each fact lives

| Fact | Home |
|---|---|
| Platforms: requirements, cost, review, link type, steps, verified flag | `skills/plan/catalog.json` |
| Monetization channels and their revenue terms | `skills/plan/catalog.json` rows with `category: "monetize"` |
| How to build an asset or a platform's integration | `skills/build/recipes/<id>.md` |
| Pricing, packaging, paywalls | `marketingskills:pricing`, `paywalls`, `offers` (not duplicated here) |
| Asset vocabulary and detection | `skills/plan/scripts/scan.py` (`ASSETS`, `detect`) |
| Generic launch/AI/SaaS directories, backlink verification, tracker format | `marketingskills:directory-submissions` (not duplicated here) |
| Per-project state | `<project>/.visibility/` (PRODUCT.md, SCAN.md, PLAN.md, MONETIZE.md, LEDGER.csv; git-ignored) |

Catalog rows marked `verified: no` come from secondhand sources; `register` re-checks the live page before using one. DR figures are as claimed by the source.

## Install

```bash
claude plugin marketplace add OrenSegal/visibility
claude plugin install visibility@visibility
```

Locally: `claude plugin marketplace add ~/Documents/GitHub/visibility`.

Gemini CLI: `gemini extensions install https://github.com/OrenSegal/visibility`. Other agents: `npx skills add OrenSegal/visibility`.

## Extend

Add a platform: one object in `catalog.json`, using asset ids from `ASSETS`; add an asset: one `ASSETS` entry and, if a file can prove it, one branch in `detect`. Add a paying channel: a catalog row with `category: "monetize"` and a `revenue` line. Add a recipe: `skills/build/recipes/<asset-or-platform-id>.md` with a `source` URL and load date. Then run the checks in `AGENTS.md`.
