"""What scan.py counts as an asset, and what it refuses to scan. Run: python3 -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import unittest

SCAN = os.path.join(os.path.dirname(__file__), "..", "skills", "plan", "scripts", "scan.py")
sys.path.insert(0, os.path.dirname(SCAN))
import scan  # noqa: E402


class MatcherTest(unittest.TestCase):
    def tree(self, files):
        d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, d)
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
            open(os.path.join(d, rel), "w").write(text)
        return d

    def test_fixtures_and_tests_are_not_assets(self):
        found = scan.detect(self.tree({"tests/fixtures/manifest.json": '{"manifest_version": 3}',
                                       "test/openapi.json": "{}", "src/__fixtures__/Dockerfile": "FROM scratch\n"}))
        self.assertEqual(set(found) & set(scan.ASSETS), set())

    def test_skill_md_needs_frontmatter_with_a_name(self):
        self.assertNotIn("skill-md", scan.detect(self.tree({"docs/SKILL.md": "# notes about skills\n"})))
        self.assertIn("skill-md", scan.detect(self.tree({"skills/x/SKILL.md": "---\nname: x\ndescription: y\n---\nbody\n"})))

    def test_truncated_walk_says_so(self):
        d = self.tree({f"a/f{i}.txt": "" for i in range(6)})
        old, scan.MAX_FILES = scan.MAX_FILES, 3
        try:
            md, data = scan.report(d, set(), [])
        finally:
            scan.MAX_FILES = old
        self.assertIn("Incomplete scan: stopped after 3 files", md)
        self.assertTrue(data["truncated"])
        self.assertFalse(scan.report(d, set(), [])[1]["truncated"])

    def test_missing_root_exits_2(self):
        r = subprocess.run([sys.executable, SCAN, os.path.join(tempfile.gettempdir(), "no-such-project")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn("not a directory", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_tracked_build_folder_is_scanned_and_untracked_one_is_not(self):
        d = self.tree({"skills/build/SKILL.md": "---\nname: build\n---\n", "dist/manifest.json": '{"manifest_version": 3}'})
        self.assertEqual(set(scan.detect(d)) & set(scan.ASSETS), set())  # not a git repo: both are build output
        git = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True, capture_output=True)
        git("init", "-q"); git("add", "skills"); git("commit", "-qm", "x")
        found = scan.detect(d)
        self.assertEqual(found.get("skill-md"), "skills/build/SKILL.md")
        self.assertNotIn("browser-ext", found)

    def test_an_existing_npm_cli_can_be_published_without_a_public_api(self):
        ids = lambda have: {p["id"] for p, _ in scan.route(have, scan.load_catalog())[0]}
        self.assertIn("npm-cli", ids({"npm-cli"}))
        self.assertIn("npm-cli", ids({"public-api"}))
        self.assertNotIn("npm-cli", ids({"github-public"}))


if __name__ == "__main__":
    unittest.main()
