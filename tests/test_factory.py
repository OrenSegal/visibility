"""The portfolio line: plan, queue batching, listing checks, metrics. Run: python3 -m unittest discover tests"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "factory", "scripts"))
import factory  # noqa: E402

ROW = {"name": "X", "category": "skills", "submit": "https://x.example/submit", "cost": "free", "review": "none",
       "link": "l", "effort": "minutes", "source": "s", "verified": "yes"}
CATALOG = [
    {**ROW, "id": "dir", "requires": ["skill-md"], "steps": [
        "claude: write the manifest for <owner>/<repo>", "human: sign in at x.example with GitHub",
        "human: paste https://github.com/<owner>/<repo> and send it"]},
    {**ROW, "id": "reg", "requires": ["mcp-server"], "verified": "no", "steps": ["approve: publish <repo>"]},
    {**ROW, "id": "other", "requires": ["skill-md"], "see": "marketingskills:directory-submissions"},
]


class FactoryTest(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)
        self.control = os.path.join(self.d, "hq")
        os.makedirs(self.control)
        for name in ("a", "b", "off"):
            os.makedirs(os.path.join(self.d, name))
        with open(os.path.join(self.control, "portfolio.json"), "w") as f:
            json.dump({"repos": [
                {"repo": "me/b", "path": "../b", "priority": 2},
                {"repo": "me/a", "path": "../a", "priority": 1, "have": ["mcp-server"]},
                {"repo": "me/off", "path": "../off", "enabled": False},
            ]}, f)
        self.pf = factory.load_portfolio(self.control)
        self.detect = lambda path: {"skill-md": "SKILL.md"}

    def test_portfolio_orders_by_priority_and_resolves_paths(self):
        self.assertEqual([r["repo"] for r in self.pf["repos"]], ["me/a", "me/b", "me/off"])
        self.assertEqual(self.pf["repos"][0]["path"], os.path.join(self.d, "a"))

    def test_plan_adds_rows_once_and_never_moves_a_row_the_user_moved(self):
        ledger, added, gone = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        self.assertEqual(sorted((r["repo"], r["platform"]) for r in added),
                         [("me/a", "dir"), ("me/a", "other"), ("me/a", "reg"), ("me/b", "dir"), ("me/b", "other")])
        self.assertEqual({r["status"] for r in ledger}, {"planned", "queued"})  # "other" is owned elsewhere: nothing to prepare
        next(r for r in ledger if r["repo"] == "me/b" and r["platform"] == "dir")["status"] = "live"
        ledger, added, gone = factory.plan(self.pf, CATALOG, ledger, "2026-11-26", self.detect)
        self.assertEqual((added, gone), ([], []))
        self.assertEqual(next(r for r in ledger if r["repo"] == "me/b" and r["platform"] == "dir")["status"], "live")

    def test_planned_row_whose_asset_vanished_is_gone_but_a_live_one_stays(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        next(r for r in ledger if r["repo"] == "me/b" and r["platform"] == "dir")["status"] = "live"
        _, _, gone = factory.plan(self.pf, CATALOG, ledger, "2026-11-26", lambda p: {})
        self.assertEqual(sorted((r["repo"], r["platform"]) for r in gone),
                         [("me/a", "dir"), ("me/a", "other"), ("me/b", "other")])

    def test_skip_keeps_a_platform_off_the_ledger(self):
        self.pf["repos"][1]["skip"] = ["dir"]
        _, added, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        self.assertNotIn(("me/b", "dir"), {(r["repo"], r["platform"]) for r in added})

    def test_skipping_a_planned_row_marks_it_skipped_not_gone(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        self.pf["repos"][1]["skip"] = ["dir"]
        ledger, _, gone = factory.plan(self.pf, CATALOG, ledger, "2026-11-26", self.detect)
        self.assertEqual(next(r for r in ledger if r["repo"] == "me/b" and r["platform"] == "dir")["status"], "skipped")
        self.assertEqual(gone, [])

    def test_queue_batches_by_kind_and_signs_in_once_per_platform(self):
        ledger, added, gone = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        q = factory.queue(self.pf, CATALOG, ledger, added, gone, "2026-11-19")
        self.assertIn("`dir`: write the manifest for me/a", q)
        self.assertEqual(q.count("sign in at x.example"), 1)
        self.assertIn("me/a: paste https://github.com/me/a and send it", q)
        self.assertIn("me/b: paste https://github.com/me/b and send it", q)
        self.assertIn("Repos: https://github.com/me/a, https://github.com/me/b", q)
        self.assertIn("me/a: publish a", q)
        self.assertIn("re-check the live page first", q)  # reg is verified: no
        self.assertIn("marketingskills:directory-submissions: me/a, me/b", q)
        self.assertLess(q.index("me/a: paste"), q.index("me/b: paste"))  # priority order

    def test_files_already_in_the_repo_queue_the_row_past_claude_work(self):
        catalog = CATALOG + [{**ROW, "id": "mk", "requires": ["skill-md"], "files": ["marketplace.json"],
                              "steps": ["claude: write marketplace.json", "approve: push"]}]
        open(os.path.join(self.d, "a", "marketplace.json"), "w").close()
        ledger, added, gone = factory.plan(self.pf, catalog, [], "2026-11-19", self.detect)
        status = {(r["repo"], r["platform"]): r["status"] for r in ledger}
        self.assertEqual((status[("me/a", "mk")], status[("me/b", "mk")]), ("queued", "planned"))
        q = factory.queue(self.pf, catalog, ledger, added, gone, "2026-11-19")
        self.assertNotIn("me/a\n\n- [ ] `mk`", q)
        self.assertEqual(q.count("`mk`: write marketplace.json"), 1)

    def test_package_names_are_checked_against_the_registries(self):
        with open(os.path.join(self.d, "a", "package.json"), "w") as f:
            json.dump({"name": "mine", "bin": {"mine": "x"}}, f)
        with open(os.path.join(self.d, "b", "package.json"), "w") as f:
            json.dump({"name": "taken"}, f)
        with open(os.path.join(self.d, "b", "pyproject.toml"), "w") as f:
            f.write('[project]\nname = "freepy"\nversion = "1"\n')
        regs = {"https://registry.npmjs.org/mine": (200, '{"dist-tags": {"latest": "1.0.1"}, "repository": {"url": "git+https://github.com/me/a.git"}}'),
                "https://registry.npmjs.org/taken": (200, '{"repository": "github:someone/else"}')}
        get = lambda url, h=None: regs.get(url, (404, ""))
        self.assertEqual(factory.package_notes("me/a", os.path.join(self.d, "a"), get), {"npm": "npm mine@1.0.1 is this repo's"})
        notes = factory.package_notes("me/b", os.path.join(self.d, "b"), get)
        self.assertIn("taken by another project; publish under a scope (@me/taken)", notes["npm"])
        self.assertEqual(notes["pypi"], "PyPI name freepy is free; not published yet")

    def test_fill_puts_the_owner_into_github_urls(self):
        self.assertEqual(factory.fill("url: https://github.com/<repo>.git, add OWNER/REPO, slug <product>", "me/a"),
                         "url: https://github.com/me/a.git, add me/a, slug a")

    def test_link_rel_reads_the_anchor_to_the_repo(self):
        html = ('<a href="https://github.com/me/ab">no</a><a rel="nofollow ugc" href="https://github.com/me/a">x</a>')
        self.assertEqual(factory.link_rel(html, "me/a"), "nofollow ugc")
        self.assertEqual(factory.link_rel('<a href="https://github.com/me/a/">x</a>', "me/a"), "dofollow (no rel)")
        self.assertEqual(factory.link_rel('<a href="https://github.com/me/ab">x</a>', "me/a"), "")

    def test_verify_records_rel_and_marks_a_vanished_listing(self):
        ledger = [
            {"repo": "me/a", "platform": "dir", "status": "submitted", "listing_url": "https://x.example/a",
             "link_rel": "", "date": "", "notes": ""},
            {"repo": "me/b", "platform": "dir", "status": "live", "listing_url": "https://x.example/b",
             "link_rel": "nofollow", "date": "", "notes": ""},
        ]
        pages = {"https://x.example/a": (200, '<a href="https://github.com/me/a" rel="nofollow">a</a>'),
                 "https://x.example/b": (404, "")}
        changed = factory.verify(ledger, lambda url, h=None: pages[url], "2026-11-19")
        self.assertEqual([(r["status"], r["link_rel"]) for r in ledger], [("live", "nofollow"), ("rejected", "nofollow")])
        self.assertEqual(len(changed), 2)

    def test_metrics_and_report_show_deltas_and_attribute_referrers(self):
        with open(os.path.join(self.d, "a", "package.json"), "w") as f:
            json.dump({"name": "a-cli"}, f)
        responses = {
            "https://api.github.com/repos/me/a": (200, '{"stargazers_count": 12, "forks_count": 1}'),
            "https://api.github.com/repos/me/a/traffic/views": (200, '{"uniques": 40}'),
            "https://api.github.com/repos/me/a/traffic/popular/referrers":
                (200, '[{"referrer": "x.example", "uniques": 9}, {"referrer": "google.com", "uniques": 3}]'),
            "https://api.npmjs.org/downloads/point/last-week/a-cli": (200, '{"downloads": 77}'),
        }
        get = lambda url, h=None: responses.get(url, (404, ""))
        ledger = [{"repo": "me/a", "platform": "dir", "status": "live", "listing_url": "https://x.example/a",
                   "link_rel": "", "date": "", "notes": ""}]
        responses["https://x.example/a"] = (200, '<a href="https://github.com/me/a">a</a>')
        history = [{"date": "2026-11-12", "repo": "me/a", "metric": "stars", "value": "10"}]
        md, rows = factory.report(self.pf, CATALOG, ledger, history, "2026-11-19", get, token="t")
        self.assertIn("| me/a | 1 | 12 (+2) | 40 | 77 | - | x.example = dir 9; google.com 3 |", md)
        self.assertIn({"date": "2026-11-19", "repo": "me/a", "metric": "npm_week", "value": "77"}, rows)
        self.assertNotIn("me/off", md)

    def test_next_returns_the_top_priority_prepare_task_with_filled_steps(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        found = factory.tasks(self.pf, CATALOG, ledger)
        self.assertEqual([(t["repo"], t["platform"]) for t in found[:2]], [("me/a", "dir"), ("me/b", "dir")])
        top = found[0]
        self.assertEqual(top["steps"]["claude"], ["write the manifest for me/a"])
        self.assertEqual(top["kind"], "prepare")
        self.assertIn("--status queued", top["then"])
        self.assertEqual(factory.tasks(self.pf, CATALOG, ledger, repo="me/b")[0]["repo"], "me/b")
        self.assertNotIn("me/off", {t["repo"] for t in found})

    def test_approve_and_human_tasks_hide_claude_steps_and_wait_for_their_status(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        # reg has only an approve: step, so it starts queued; dir still needs Claude's prepare step first
        approve = factory.tasks(self.pf, CATALOG, ledger, "approve")
        self.assertEqual([(t["repo"], t["platform"], t["steps"]) for t in approve],
                         [("me/a", "reg", {"approve": ["publish a"], "human": []})])
        self.assertEqual(factory.tasks(self.pf, CATALOG, ledger, "human"), [])
        factory.done(ledger, "me/a", "dir", "waiting-on-user", today="d")
        human = factory.tasks(self.pf, CATALOG, ledger, "human")
        self.assertEqual([(t["repo"], t["platform"]) for t in human], [("me/a", "dir")])
        self.assertEqual(list(human[0]["steps"]), ["approve", "human"])
        self.assertEqual(len(human[0]["steps"]["human"]), 2)
        self.assertIsNone(human[0]["scope"])

    def test_done_validates_and_records(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        row = factory.done(ledger, "me/a", "dir", "queued", note="wrote manifest", today="2026-11-20")
        self.assertEqual((row["status"], row["notes"], row["date"]), ("queued", "wrote manifest", "2026-11-20"))
        for args in (("me/a", "dir", "bogus"), ("me/zz", "dir", "queued"), ("me/a", "dir", "live"),
                     ("me/a", "dir", "submitted", "ftp://x")):
            with self.assertRaises(ValueError, msg=args):
                factory.done(ledger, *args)
        factory.done(ledger, "me/a", "dir", "live", url="https://x.example/a", today="d")
        self.assertEqual(ledger[0]["listing_url"] if ledger[0]["platform"] == "dir" else "", "https://x.example/a")

    def test_prepare_tasks_carry_only_claude_steps_and_rows_without_any_start_queued(self):
        catalog = CATALOG + [{**ROW, "id": "form", "requires": ["skill-md"], "steps": ["human: submit the form"]}]
        ledger, _, _ = factory.plan(self.pf, catalog, [], "2026-11-19", self.detect)
        self.assertEqual({r["platform"]: r["status"] for r in ledger if r["repo"] == "me/a"}["form"], "queued")
        self.assertEqual({r["platform"]: r["status"] for r in ledger if r["repo"] == "me/a"}["other"], "queued")  # see:
        for t in factory.tasks(self.pf, catalog, ledger):
            self.assertEqual(list(t["steps"]), ["claude"])
            self.assertIn("Do not publish", t["scope"])

    def test_status_counts_enabled_repos_and_lists_blocked_rows(self):
        ledger, _, _ = factory.plan(self.pf, CATALOG, [], "2026-11-19", self.detect)
        factory.done(ledger, "me/a", "reg", "waiting-on-user", note="pick a package name", today="d")
        st = factory.status(self.pf, ledger)
        self.assertEqual(sorted(st["repos"]), ["me/a", "me/b"])
        self.assertEqual(st["repos"]["me/a"], {"planned": 1, "queued": 1, "waiting-on-user": 1})
        self.assertEqual(st["waiting_on_user"], [{"repo": "me/a", "platform": "reg", "why": "pick a package name"}])

    def repo_tree(self, files):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d)
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)) or d, exist_ok=True)
            with open(os.path.join(d, rel), "w") as f:
                f.write(text)
        return d

    GOOD_CI = ("name: ci\non:\n  pull_request:\npermissions:\n  contents: read\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
               "    timeout-minutes: 10\n    steps:\n      - uses: actions/checkout@" + "a" * 40 + " # v7\n      - uses: ./local\n")

    def test_baseline_passes_a_hardened_repo(self):
        d = self.repo_tree({"LICENSE": "MIT", "README.md": "x", "SECURITY.md": "x", "tests/test_a.py": "",
                            ".github/workflows/ci.yml": self.GOOD_CI,
                            ".github/dependabot.yml": "updates:\n  - package-ecosystem: github-actions\n",
                            "package.json": '{"version": "1.2.0"}', "gemini-extension.json": '{"version": "1.2.0"}'})
        res = factory.baseline(d)
        self.assertEqual([c for c, (ok, _) in res.items() if not ok], [])
        self.assertEqual(set(res), set(factory.CHECKS))

    def test_baseline_names_each_gap(self):
        ci = ("on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - uses: actions/checkout@v4\n"
              "      - uses: docker://alpine:3\n  b:\n    runs-on: x\n    timeout-minutes: 5\n")
        d = self.repo_tree({"README.md": "x", ".github/workflows/ci.yml": ci,
                            "package.json": '{"version": "1.0.0"}', ".claude-plugin/plugin.json": '{"version": "1.1.0"}'})
        res = factory.baseline(d)
        failing = {c for c, (ok, _) in res.items() if not ok}
        self.assertEqual(failing, {"license", "security-policy", "tests-exist", "ci-on-pr", "workflow-permissions",
                                   "workflow-timeouts", "actions-pinned", "dependabot", "versions-agree"})
        self.assertIn("actions/checkout@v4", res["actions-pinned"][1])
        self.assertNotIn("docker://", res["actions-pinned"][1])
        self.assertIn("ci.yml", res["workflow-timeouts"][1])  # job a has no timeout, job b does
        self.assertIn("package.json 1.0.0", res["versions-agree"][1])

    def test_baseline_community_defaults_stand_in_for_a_security_policy(self):
        d = self.repo_tree({"README.md": "x"})
        self.assertFalse(factory.baseline(d)["security-policy"][0])
        self.assertTrue(factory.baseline(d, community_defaults=True)["security-policy"][0])

    def test_baseline_with_no_workflows_fails_the_ci_check_not_the_others_it_cannot_judge(self):
        res = factory.baseline(self.repo_tree({"README.md": "x"}))
        self.assertFalse(res["ci-on-pr"][0])
        self.assertTrue(res["workflow-permissions"][0] and res["workflow-timeouts"][0] and res["actions-pinned"][0])

    def test_ledger_round_trips(self):
        path = os.path.join(self.control, "LEDGER.csv")
        rows = [{c: "" for c in factory.LEDGER_COLS} | {"repo": "me/a", "platform": "dir", "notes": "a, \"b\""}]
        factory.write_csv(path, factory.LEDGER_COLS, rows)
        self.assertEqual(factory.read_csv(path, factory.LEDGER_COLS), rows)


if __name__ == "__main__":
    unittest.main()
