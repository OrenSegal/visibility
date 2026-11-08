import json
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

    def test_either_or_requirement(self):
        cat = scan.load_catalog()
        ids = lambda have: {p["id"] for p, _ in scan.route(have, cat)[0]}
        self.assertIn("cursor-directory", ids({"github-public", "skill-md"}))
        self.assertIn("cursor-directory", ids({"github-public", "mcp-server"}))
        self.assertNotIn("cursor-directory", ids({"github-public"}))

    def test_rejects_unknown_declared_asset(self):
        r = subprocess.run([sys.executable, SCAN, ".", "--have", "nope"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown asset", r.stderr)


if __name__ == "__main__":
    unittest.main()
