# Working on visibility

Before committing, all of these pass:

```bash
python3 skills/plan/scripts/scan.py --check
python3 -m unittest discover tests
claude plugin validate .
```

Each fact has one home; the table in `README.md` says where. A platform step starts with `claude:`, `approve:` or `human:`; account creation, payment, DNS, credentials and form submission are always `human:`.

Skills that run without their siblings read the catalog and recipes from a pinned commit (`raw.githubusercontent.com/OrenSegal/visibility/<sha>/...`), never `main`. After a catalog or recipe change is reviewed and pushed, move every pin to that commit in one follow-up commit; the tests reject a branch name or an unknown sha.
