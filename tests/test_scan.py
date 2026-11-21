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
            "go.mod": "module example.com/x",
        }
        with tempfile.TemporaryDirectory() as d:
            for rel, text in files.items():
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                open(os.path.join(d, rel), "w").write(text)
            found = set(scan.detect(d))
        self.assertTrue({"apify-actor", "cursor-plugin", "teams-app", "forge-app", "workspace-addon", "jsr-package", "go-module"} <= found)
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

    def test_public_repo_is_detected_without_gh(self):
        import io
        from unittest import mock
        calls = []

        def fake_urlopen(req, timeout):
            calls.append(req.full_url)
            if "secret" in req.full_url:
                raise OSError("404")
            return io.StringIO('{"private": false}')

        with mock.patch.object(scan.subprocess, "run", side_effect=OSError("no gh")), \
                mock.patch.object(scan.urllib.request, "urlopen", fake_urlopen):
            self.assertTrue(scan.is_public("https://github.com/acme/tool.git"))
            self.assertTrue(scan.is_public("git@github.com:acme/tool.git"))
            self.assertFalse(scan.is_public("https://github.com/acme/secret"))
            self.assertFalse(scan.is_public("https://example.com/acme/tool"))
        self.assertEqual(calls[:2], ["https://api.github.com/repos/acme/tool"] * 2)

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

    def test_installs_are_pinned_and_never_a_claude_step(self):
        import glob
        root = os.path.join(os.path.dirname(__file__), "..")
        cmd = re.compile(r"\b(?:npx|npm (?:create|i|install)|brew install|pip3? install|pipx run|uvx)\b[^`;|&(),]*")
        pin = re.compile(r"^(?:@[\w.-]+/)?[\w.-]+@\d[\w.+-]*$")
        lines = []  # (where, text)
        for f in sorted(glob.glob(os.path.join(root, "skills", "*", "recipes", "*.md"))):
            lines += [(os.path.basename(f) + ":" + str(i + 1), t) for i, t in enumerate(open(f).read().splitlines())]
        for p in scan.load_catalog():
            for k in ("steps", "artifacts", "notes"):
                v = p.get(k) or []
                lines += [(p["id"] + "." + k, t) for t in ([v] if isinstance(v, str) else v)]
        bad = []
        for where, text in lines:
            if "@latest" in text or re.search(r"curl[^|]*\|\s*(ba)?sh", text):
                bad.append(f"{where}: @latest or curl | sh")
            for m in cmd.finditer(text):
                toks = [t.strip("`'\"") for t in m.group(0).split()]
                if toks[0] == "brew":
                    if "brew info" not in text:
                        bad.append(f"{where}: brew install needs a 'brew info' version check on the same line")
                    continue
                if toks[0] in ("pip", "pip3", "pipx", "uvx"):
                    if not re.search(r"==|@\d", m.group(0)):
                        bad.append(f"{where}: unpinned {toks[0]}")
                    continue
                if toks[:2] == ["npm", "create"] or toks[0] == "npx":
                    names, i = [], 2 if toks[0] == "npm" else 1
                    while i < len(toks) and toks[i] != "--":
                        if toks[i] in ("--package", "-p") and i + 1 < len(toks):
                            names.append(toks[i + 1]); i += 2; continue
                        if not toks[i].startswith("-"):
                            names.append(toks[i]); break
                        i += 1
                else:  # npm i / install: every named package
                    names = [t for t in toks[2:] if not t.startswith("-") and t != "--"]
                bad += [f"{where}: {n} is not pinned to an exact version" for n in names if not pin.match(n)]
            if re.match(r"\s*claude: ", text) and cmd.search(text):
                bad.append(f"{where}: an install command must be an approve: step")
        self.assertEqual(bad, [])

    def test_ranks_by_listing_host_traffic(self):
        row = lambda i, rank, effort="minutes": {"id": i, "requires": [], "effort": effort,
                                                 **({"traffic": {"host": i, "rank": rank}} if rank != "none" else {})}
        cat = [row("quiet", None), row("busy", 500), row("mid", 50_000), row("nohost", "none"), row("busy-slow", 500, "weeks")]
        self.assertEqual([p["id"] for p, _ in scan.route(set(), cat)[0]], ["busy", "busy-slow", "mid", "quiet", "nohost"])
        bad = {**row("x", 0), "name": "x", "category": "c", "submit": "s", "cost": "c", "review": "r", "link": "l",
               "source": "s", "verified": "no", "steps": ["human: x"]}
        self.assertIn("x: traffic must be {host, rank} with a positive integer rank or null", scan.check([bad]))

    def test_skips_agent_config_and_honours_declared_public_repo(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in (".claude/worktrees/a/skills/x/SKILL.md", ".agents/skills/x/SKILL.md"):
                os.makedirs(os.path.dirname(os.path.join(d, rel)))
                open(os.path.join(d, rel), "w").write("---\nname: x\n---\n")
            subprocess.run(["git", "init", "-q", d], check=True)
            subprocess.run(["git", "-C", d, "remote", "add", "origin", "https://github.com/o/r.git"], check=True)
            old, scan.is_public = scan.is_public, lambda origin: False  # as when gh and the API cannot tell
            try:
                self.assertNotIn("skill-md", scan.detect(d))
                self.assertIn("not counted as public", scan.report(d, set(), [])[0])
                self.assertNotIn("not counted as public", scan.report(d, {"github-public"}, [])[0])
            finally:
                scan.is_public = old

    def test_rejects_unknown_declared_asset(self):
        r = subprocess.run([sys.executable, SCAN, ".", "--have", "nope"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown asset", r.stderr)

    def test_verified_yes_needs_an_observed_link(self):
        row = {"id": "x", "name": "X", "category": "mcp", "submit": "u", "requires": ["github-public"], "cost": "free",
               "review": "none", "link": "unchecked", "effort": "minutes", "source": "s", "verified": "yes",
               "steps": ["human: sign up"]}
        errors = lambda r: [e for e in scan.check([r]) if e.startswith("x:")]
        self.assertEqual(errors(row), ["x: verified is yes but link is unchecked; use flow until the listing's link is observed"])
        self.assertEqual(errors({**row, "verified": "flow"}), [])
        self.assertEqual(errors({**row, "link": "rel=ugc nofollow (observed)"}), [])

    def test_report_prints_traffic_and_says_when_unmeasured(self):
        row = lambda i, t: {"id": i, "name": i, "category": "mcp", "submit": "u", "requires": [], "cost": "free",
                            "review": "none", "link": "l", "effort": "minutes", "source": "s", "verified": "no",
                            "steps": ["human: x"], **({"traffic": t} if t else {})}
        cat = [row("busy", {"host": "busy.example", "rank": 1234}), row("quiet", {"host": "quiet.example", "rank": None}),
               row("inapp", None)]
        with tempfile.TemporaryDirectory() as d:
            md, _ = scan.report(d, set(), cat)
        self.assertIn("| `busy` busy | busy.example #1,234 |", md)
        self.assertIn("| `quiet` quiet | quiet.example (not in top 1M) |", md)
        self.assertIn("| `inapp` inapp | no host to measure |", md)
    def test_linkcheck_separates_dead_from_blocked(self):
        import http.server
        import importlib.util
        import threading
        spec = importlib.util.spec_from_file_location(
            "linkcheck", os.path.join(os.path.dirname(__file__), "..", ".github", "linkcheck.py"))
        linkcheck = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(linkcheck)

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(int(self.path.strip("/")))
                self.end_headers()

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/"
            kinds = {code: linkcheck.classify(linkcheck.status(base + str(code))) for code in (200, 404, 410, 403, 429)}
        finally:
            server.shutdown()
        self.assertEqual(kinds, {200: "ok", 404: "dead", 410: "dead", 403: "blocked", 429: "blocked"})
        self.assertEqual(linkcheck.classify(linkcheck.status("http://127.0.0.1:1/")), "unreachable")


if __name__ == "__main__":
    unittest.main()
