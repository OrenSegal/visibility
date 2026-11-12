#!/usr/bin/env python3
"""Report catalog `submit` URLs that no longer resolve.

Usage: linkcheck.py [catalog.json]

dead        = 404 or 410: the row needs a look. Exit 1 if any.
unreachable = no HTTP answer on two tries (DNS, TLS, timeout, refused). Printed, and as a warning annotation in
              GitHub Actions, but not a failure: one run cannot tell a gone host from a bad minute.
blocked     = 401, 403, 429 and other statuses: a login or bot wall, which says nothing about the page.
A 200 only means the URL answers; it does not show that the submission flow is unchanged.
"""
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "plan", "catalog.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (catalog link check)", "Accept": "text/html,*/*"}


def status(url, timeout=20):
    """HTTP status after redirects (GET, since several sites answer HEAD differently), or 0 when nothing answers twice."""
    # second try without certificate checks: some hosts serve an incomplete chain, and this asks only whether the
    # page answers; nothing is sent to it and nothing it returns is used
    for context in (None, ssl._create_unverified_context()):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout, context=context) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, OSError, ValueError):
            pass
    return 0


def classify(code):
    return "ok" if 200 <= code < 300 else "dead" if code in (404, 410) else "blocked" if code else "unreachable"


def main():
    with open(sys.argv[1] if len(sys.argv) > 1 else CATALOG, encoding="utf-8") as f:
        rows = [(p["id"], p["submit"].split()[0]) for p in json.load(f)["platforms"] if p["submit"].startswith("http")]
    results = [(pid, url, status(url)) for pid, url in rows]
    for kind in ("dead", "unreachable", "blocked"):
        for pid, url, code in results:
            if classify(code) == kind:
                print(f"{kind}\t{code or 'no answer'}\t{pid}\t{url}")
                if kind == "unreachable" and os.environ.get("GITHUB_ACTIONS"):
                    print(f"::warning::{pid}: no answer from {url}")
    count = lambda kind: sum(classify(code) == kind for _, _, code in results)
    print(f"{len(results)} submit URLs: {count('dead')} dead, {count('unreachable')} unreachable, {count('blocked')} blocked")
    return 1 if count("dead") else 0


if __name__ == "__main__":
    sys.exit(main())
