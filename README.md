# visibility

Get a product listed on high-authority agent, integration, extension and API marketplaces: a dedicated page, an install button, often a backlink. Two Agent Skills for Claude Code.

| Skill | Use it to |
|---|---|
| `/visibility:plan [path ...] [--portfolio]` | Detect listable assets (MCP server, Agent Skill, Claude plugin, OpenAPI, npm CLI, browser/VS Code/Raycast/Obsidian extension, GitHub Action, llms.txt, iOS app), ask for the ones files cannot prove (remote MCP URL, OAuth, public API, domain, test account), and rank where it can be listed now and which one asset unlocks the most listings. |
| `/visibility:register <platform-id>` | Walk one platform end to end: re-check the live submission page, build the artifacts, run publish commands after an explicit yes, hand account/payment/DNS/form steps to you, verify the listing and update the ledger. |

Both are user-invoked. Nothing is published, paid for or submitted without you.

## Where each fact lives

| Fact | Home |
|---|---|
| Platforms: requirements, cost, review, link type, steps, verified flag | `skills/plan/catalog.json` |
| Asset vocabulary and detection | `skills/plan/scripts/scan.py` (`ASSETS`, `detect`) |
| Generic launch/AI/SaaS directories, backlink verification, tracker format | `marketingskills:directory-submissions` (not duplicated here) |
| Per-project state | `<project>/.visibility/` (PRODUCT.md, SCAN.md, PLAN.md, LEDGER.csv; git-ignored) |

Catalog rows marked `verified: no` come from secondhand sources; `register` re-checks the live page before using one. DR figures are as claimed by the source.

## Install

```bash
claude plugin marketplace add OrenSegal/visibility
claude plugin install visibility@visibility
```

Locally: `claude plugin marketplace add ~/Documents/GitHub/visibility`.

## Extend

Add a platform: one object in `catalog.json`, using asset ids from `ASSETS`; add an asset: one `ASSETS` entry and, if a file can prove it, one branch in `detect`. Then run the checks in `AGENTS.md`.
