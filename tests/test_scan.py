import json
import re
import os
import subprocess
import sys
import tempfile
import unittest

SCAN = os.path.join(os.path.dirname(__file__), "..", "skills", "plan", "scripts", "scan.py")
sys.path.insert(0, os.path.dirname(SCAN))
import scan  # noqa: E402


class ScanTest(unittest.TestCase):
    def test_catalog_is_consistent(self):
        self.assertEqual(scan.check(scan.load_catalog()), [])

    def test_detects_assets_and_routes(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "ext"))
            os.makedirs(os.path.join(d, "skills", "x"))
            os.makedirs(os.path.join(d, "node_modules", "junk"))
            open(os.path.join(d, "ext", "manifest.json"), "w").write('{"manifest_version": 3}')
            open(os.path.join(d, "skills", "x", "SKILL.md"), "w").write("---\nname: x\n---\n")
            open(os.path.join(d, "node_modules", "junk", "openapi.json"), "w").write("{}")  # skipped dir
            open(os.path.join(d, "package.json"), "w").write(json.dumps(
                {"name": "x", "bin": {"x": "cli.js"}, "dependencies": {"@modelcontextprotocol/sdk": "1"}}))
            found = scan.detect(d)
            self.assertTrue({"browser-ext", "skill-md", "npm-cli", "mcp-server"} <= set(found))
            self.assertNotIn("openapi", found)

            eligible, unlocks, _ = scan.route(set(found), scan.load_catalog())
            ids = {p["id"] for p, _ in eligible}
            self.assertIn("chrome-web-store", ids)
            self.assertIn("mcp-registry", ids)
            self.assertNotIn("smithery", ids)  # needs a live remote URL, which only --have declares
            self.assertIn("mcp-remote", dict(unlocks))

    def test_detects_marketplace_app_manifests(self):
        files = {
            ".actor/actor.json": "{}",
            ".cursor-plugin/plugin.json": "{}",
            "teams/manifest.json": '{"$schema": "https://developer.microsoft.com/json-schemas/teams/v1.19/MicrosoftTeams.schema.json"}',
            "forge/manifest.yml": "modules:\n  jira:issuePanel: []\napp:\n  id: ari:x\n",
            "addon/appsscript.json": '{"addOns": {}}',
            "jsr.json": "{}",
        }
        with tempfile.TemporaryDirectory() as d:
            for rel, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                open(os.path.join(d, rel), "w").write(text)
            found = set(scan.detect(d))
        self.assertTrue({"apify-actor", "cursor-plugin", "teams-app", "forge-app", "workspace-addon", "jsr-package"} <= found)
        self.assertNotIn("browser-ext", found)

    def test_either_or_requirement(self):
        cat = scan.load_catalog()
        ids = lambda have: {p["id"] for p, _ in scan.route(have, cat)[0]}
        self.assertIn("cursor-directory", ids({"github-public", "skill-md"}))
        self.assertIn("cursor-directory", ids({"github-public", "mcp-server"}))
        self.assertNotIn("cursor-directory", ids({"github-public"}))

    def test_monetize_rows_need_revenue_and_report_apart(self):
        row = {"id": "x-pay", "name": "X", "category": "monetize", "submit": "u", "requires": ["github-public"],
               "cost": "free", "review": "none", "link": "none", "effort": "minutes", "source": "s",
               "verified": "no", "steps": ["human: sign up"]}
        rows = lambda r: [e for e in scan.check([r]) if e.startswith("x-pay")]
        self.assertEqual(rows(row), ["x-pay: monetize rows need revenue (fee, rev share, payout minimum)"])
        self.assertEqual(rows({**row, "revenue": "5%"}), [])
        eligible, _, _ = scan.route({"github-public"}, [{**row, "revenue": "5%"}])
        self.assertEqual([p["id"] for p, _ in eligible], ["x-pay"])

    def test_recipes_are_named_for_known_ids(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "browser-ext.md"), "w").write("x")
            open(os.path.join(d, "n8n.md"), "w").write("x")
            open(os.path.join(d, "nope.md"), "w").write("x")
            old, scan.RECIPES = scan.RECIPES, d
            try:
                self.assertEqual(scan.check(scan.load_catalog()), ["recipes/nope.md: not an asset or platform id"])
            finally:
                scan.RECIPES = old

    def test_fallback_urls_are_pinned_to_a_real_commit(self):
        import glob
        root = os.path.join(os.path.dirname(__file__), "..")
        urls = []
        for f in glob.glob(os.path.join(root, "skills", "*", "SKILL.md")):
            urls += re.findall(r"https://raw\.githubusercontent\.com/OrenSegal/visibility/([^/\s]+)/", open(f).read())
        self.assertTrue(urls)
        for ref in urls:
            self.assertRegex(ref, r"^[0-9a-f]{40}$", "fallback must pin a full commit sha, not a branch")
            r = subprocess.run(["git", "-C", root, "cat-file", "-e", ref + "^{commit}"], capture_output=True)
            self.assertEqual(r.returncode, 0, f"pinned commit {ref} not in this repo")

    def test_rejects_unknown_declared_asset(self):
        r = subprocess.run([sys.executable, SCAN, ".", "--have", "nope"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown asset", r.stderr)


if __name__ == "__main__":
    unittest.main()
