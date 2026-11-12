"""Catalog steps: who may do what. Run: python3 -m unittest discover tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "skills", "plan", "scripts"))
import scan  # noqa: E402


class StepTest(unittest.TestCase):
    def test_non_human_steps_cannot_sign_in_submit_pay_or_hold_credentials(self):
        row = {"id": "x", "name": "X", "category": "mcp", "submit": "u", "requires": ["github-public"], "cost": "free",
               "review": "none", "link": "l", "effort": "minutes", "source": "s", "verified": "no"}
        errors = lambda *steps: [e for e in scan.check([{**row, "steps": list(steps)}]) if e.startswith("x:")]
        for step in ("approve: paste the repo URL and Submit for free", "claude: validate the package in the Developer Portal",
                     "approve: npx tool publish -p <token>", "claude: sign in and pay the fee"):
            self.assertEqual(len(errors(step)), 1, step)
        self.assertEqual(errors("human: sign in, pay and submit the form", "approve: npm publish --access public",
                                "claude: follow the checklist at example.com/docs/plugins/submit",
                                "claude: draft the submission email", "claude: return 402 with payment requirements"), [])


if __name__ == "__main__":
    unittest.main()
