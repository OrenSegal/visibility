---
name: monetize
description: Find where a project can earn money through the platforms it can be listed on - paid API plans, marketplace actors, cloud marketplaces, sponsorships, merchant-of-record stores, paid plugins, pay-per-call agent payments - ranked by fee, payout terms and effort, then set up one channel at a time.
disable-model-invocation: true
argument-hint: "[path] [--channel <id>]"
metadata:
  openclaw:
    homepage: https://github.com/OrenSegal/visibility
    requires:
      bins: [python3, git]
---

Find the channels in the visibility catalog that pay, rank them, and set one up. The channels are catalog rows with `category: "monetize"`, each with a `revenue` line (platform fee or revenue share, payout minimum). The catalog lives in `../plan/catalog.json` (resolve from this file's directory). If this skill was installed alone, read it from https://raw.githubusercontent.com/OrenSegal/visibility/main/skills/plan/catalog.json.

What to charge, how to package plans and how to write the paywall belong elsewhere: `marketingskills:pricing`, `marketingskills:paywalls` and `marketingskills:offers` if installed. This skill only decides which channels and in what order.

## Rules

- **Facts come from the row.** Fees and payout terms change. For a row with `verified: no`, or one whose `source` date is older than 90 days, open the official page before quoting a number, and update the row if the number changed.
- **Money steps are always `human:`.** That covers payout and tax details, merchant accounts, bank and card data, identity verification and accepting seller agreements. Claude prepares the listing copy, plan tiers and code, then hands over a checklist.
- **Don't break the free path.** A paid channel must not remove the free listing, install or API key that existing users rely on. Say so if one would.
- **Prefer channels that also list the product.** A channel that earns and gives a public page (such as a paid plan on an API hub) beats one that only earns.

## Steps

1. **Facts.** Reuse `.visibility/PRODUCT.md` if it exists; otherwise run step 1 of `../plan/SKILL.md`. Add what monetization needs: is the product paid today, and through what (Stripe, App Store, none)? Who pays: developers, businesses or consumers? Is it usage-based?
2. **Scan.** Run `python3 ../plan/scripts/scan.py <path> --have <confirmed assets>` and read the "Earn now" table. "One asset away" rows in the `monetize` category are channels unlocked by building one asset (see `/visibility:build`).
3. **Rank** the eligible channels by fit for who pays. Developer tools suit API hubs, marketplaces, sponsorships and pay-per-call; B2B suits cloud marketplaces; consumers suit stores. Within each group, rank by take rate, then effort. Write `.visibility/MONETIZE.md` with three sections: Now (at most three channels: why each, the fee, what Claude prepares, the user's `human:` steps), Build next (an asset that unlocks a better channel), and Skip (with the reason).
4. **Set up one channel** (`--channel <id>`, or the top pick after a yes). Run its row the way `../register/SKILL.md` does: re-check the live page, build the artifacts, wait for a yes before any `approve:` step, and hand over the `human:` steps.
5. **Ledger.** Add or update the row in `.visibility/LEDGER.csv` with status `planned`, `waiting-on-user` or `live`, and note the revenue terms you confirmed.

Done when MONETIZE.md exists and either one channel is live or the user holds its remaining `human:` checklist.
