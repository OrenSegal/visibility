# Working on visibility

Before committing, all of these pass:

```bash
python3 skills/plan/scripts/scan.py --check
python3 -m unittest discover tests
claude plugin validate .
```

Each fact has one home; the table in `README.md` says where. A platform step starts with `claude:`, `approve:` or `human:`; account creation, payment, DNS, credentials and form submission are always `human:`.
