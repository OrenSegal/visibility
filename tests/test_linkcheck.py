"""The catalog link check skips placeholder URLs. Run: python3 -m unittest discover tests"""
import importlib.util
import os
import unittest

PATH = os.path.join(os.path.dirname(__file__), "..", ".github", "linkcheck.py")
spec = importlib.util.spec_from_file_location("linkcheck", PATH)
linkcheck = importlib.util.module_from_spec(spec)
spec.loader.exec_module(linkcheck)


class LinkcheckTest(unittest.TestCase):
    def test_placeholder_and_non_url_submits_are_not_checked(self):
        rows = [
            {"id": "real", "submit": "https://example.com/submit (sign in first)"},
            {"id": "template", "submit": "https://github.com/<owner>/<repo> (About settings)"},
            {"id": "prose", "submit": "your own homebrew-<name> repo"},
        ]
        self.assertEqual(linkcheck.submit_urls(rows), [("real", "https://example.com/submit")])

    def test_the_real_catalog_has_no_placeholder_left_in_the_checked_urls(self):
        import json
        catalog = os.path.join(os.path.dirname(PATH), "..", "skills", "plan", "catalog.json")
        urls = linkcheck.submit_urls(json.load(open(catalog))["platforms"])
        self.assertTrue(urls)
        self.assertFalse([u for _, u in urls if "<" in u or ">" in u])


if __name__ == "__main__":
    unittest.main()
