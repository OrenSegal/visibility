#!/usr/bin/env python3
"""Run the visibility pipeline across a portfolio of repos from one control folder.

Usage:
  factory.py init <control-dir> <repo-path ...>     write portfolio.json from local clones
  factory.py plan <control-dir> [--date YYYY-MM-DD] [--offline]
                                                    scan every enabled repo, add new rows to LEDGER.csv, write QUEUE.md
  factory.py report <control-dir> [--date ...]      re-check live listings, record metrics, write reports/<date>.md

The control folder (a private repo such as distribution-hq) holds portfolio.json, LEDGER.csv, QUEUE.md,
METRICS.csv and reports/. Nothing here publishes, signs in or submits: QUEUE.md lists the claude: work,
the approve: commands (grouped by platform, so one yes covers a batch) and the human: checklist (grouped by
platform, so one sign-in covers every repo). Platform facts stay in ../../plan/catalog.json.
"""
import argparse
import csv
import datetime
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "plan", "scripts"))
import scan  # noqa: E402

LEDGER_COLS = ["repo", "platform", "status", "listing_url", "link_rel", "date", "notes"]
OPEN = ("planned", "queued", "waiting-on-user")  # rows the queue still has work for
STATUSES = OPEN + ("submitted", "live", "rejected", "skipped", "gone")
METRIC_COLS = ["date", "repo", "metric", "value"]


# ---------- portfolio and ledger ----------

def load_portfolio(control):
    with open(os.path.join(control, "portfolio.json"), encoding="utf-8") as f:
        pf = json.load(f)
    errors = []
    for i, r in enumerate(pf.get("repos", [])):
        where = r.get("repo", f"repos[{i}]")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", r.get("repo", "")):
            errors.append(f"{where}: repo must be owner/name")
        if not isinstance(r.get("priority", 3), int):
            errors.append(f"{where}: priority must be an integer (1 = first)")
        bad = [a for a in r.get("have", []) if a not in scan.ASSETS]
        if bad:
            errors.append(f"{where}: unknown asset(s) in have: {', '.join(bad)}")
    if errors:
        sys.exit("portfolio.json: " + "; ".join(errors))
    for r in pf["repos"]:
        r.setdefault("priority", 3)
        r.setdefault("enabled", True)
        r.setdefault("have", [])
        r.setdefault("skip", [])
        r["path"] = os.path.normpath(os.path.join(control, r.get("path", "../" + r["repo"].split("/")[1])))
    pf["repos"].sort(key=lambda r: (r["priority"], r["repo"]))
    return pf


def read_csv(path, cols):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", newline="") as f:
        return [{c: row.get(c, "") for c in cols} for row in csv.DictReader(f)]


def write_csv(path, cols, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


# ---------- plan: scan, merge, queue ----------

def fill(step, repo):
    """Put the repo's own names into a catalog step's placeholders."""
    owner, name = repo.split("/")
    step = re.sub(r"github\.com/<repo>", "github.com/<owner>/<repo>", step)  # a GitHub URL always needs the owner
    return (step.replace("<owner>/<repo>", repo).replace("OWNER/REPO", repo).replace("<owner>", owner).replace("<repo>", name)
            .replace("<product>", name).replace("<name>", name))


PACKAGE_ROWS = {"npm": ("npm-cli", "deps-dev", "homebrew-tap", "mcp-registry"),
                "pypi": ("pypi", "deps-dev", "homebrew-tap", "mcp-registry")}


def package_notes(repo, path, get):
    """{registry: note} saying whether each package the repo would publish is ours, unpublished or taken."""
    npm, pypi = package_names(path)
    notes = {}
    if npm:
        status, body = get(f"https://registry.npmjs.org/{npm}")
        if status == 404:
            notes["npm"] = f"npm name {npm} is free; not published yet"
        elif status == 200:
            d = json.loads(body)
            src = json.dumps(d.get("repository", "")) + json.dumps(d.get("homepage", ""))
            latest = d.get("dist-tags", {}).get("latest", "?")
            notes["npm"] = (f"npm {npm}@{latest} is this repo's" if repo.lower() in src.lower()
                            else f"npm name {npm} is taken by another project; publish under a scope (@{repo.split('/')[0].lower()}/{npm})")
    if pypi:
        status, body = get(f"https://pypi.org/pypi/{pypi}/json")
        if status == 404:
            notes["pypi"] = f"PyPI name {pypi} is free; not published yet"
        elif status == 200:
            info = json.loads(body).get("info", {})
            src = json.dumps(info.get("project_urls") or {}) + str(info.get("home_page") or "")
            notes["pypi"] = (f"PyPI {pypi}=={info.get('version')} is this repo's" if repo.lower() in src.lower()
                             else f"PyPI name {pypi} is taken by another project; rename before publishing")
    return notes


def plan(pf, catalog, ledger, today, detect=scan.detect, get=None):
    """Scan each enabled repo; return (ledger with new rows, new rows, rows no longer eligible).

    A new row whose catalog `files` already exist in the repo starts as `queued` (the claude: work is done).
    With `get`, rows that publish a package carry a note saying whether its name is ours, free or taken."""
    by_id = {p["id"]: p for p in catalog}
    known = {(r["repo"], r["platform"]): r for r in ledger}
    added, gone, eligible_now = [], [], set()
    for r in pf["repos"]:
        if not r["enabled"]:
            continue
        if not os.path.isdir(r["path"]):
            sys.stderr.write(f"skip {r['repo']}: no clone at {r['path']}\n")
            continue
        have = {a for a in detect(r["path"]) if a in scan.ASSETS} | set(r["have"])
        eligible, _, _ = scan.route(have, catalog)
        pkg = package_notes(r["repo"], r["path"], get) if get else {}
        for p, _ in eligible:
            if p["id"] in r["skip"]:
                continue
            eligible_now.add((r["repo"], p["id"]))
            if (r["repo"], p["id"]) not in known:
                present = p.get("files") and all(os.path.exists(os.path.join(r["path"], f)) for f in p["files"])
                notes = [f"has {', '.join(p['files'])}"] if present else []
                notes += [n for reg, n in pkg.items() if p["id"] in PACKAGE_ROWS[reg]]
                row = {"repo": r["repo"], "platform": p["id"], "status": "queued" if present else "planned",
                       "listing_url": "", "link_rel": "", "date": today, "notes": "; ".join(notes)}
                ledger.append(row)
                added.append(row)
    scanned = {r["repo"] for r in pf["repos"] if r["enabled"] and os.path.isdir(r["path"])}
    for row in ledger:  # a planned row whose asset disappeared is no longer work
        if row["repo"] in scanned and row["status"] == "planned" and (row["repo"], row["platform"]) not in eligible_now \
                and row["platform"] in by_id:
            row["status"], row["notes"], row["date"] = "gone", "no longer eligible: a required asset is missing", today
            gone.append(row)
    return ledger, added, gone


def queue(pf, catalog, ledger, added, gone, today):
    """QUEUE.md: what Claude does, what needs a yes, what only the user can do, grouped for batching."""
    by_id = {p["id"]: p for p in catalog}
    prio = {r["repo"]: r["priority"] for r in pf["repos"]}
    open_rows = sorted((row for row in ledger if row["status"] in OPEN and row["platform"] in by_id),
                       key=lambda row: (prio.get(row["repo"], 9), row["repo"]))
    claude, approve, human, owned = {}, {}, {}, {}
    for row in open_rows:
        p = by_id[row["platform"]]
        if p.get("see"):
            owned.setdefault(p["see"], []).append(row["repo"])
            continue
        for s in p.get("steps", []):
            kind, text = s.split(": ", 1)
            target = {"claude": claude, "approve": approve, "human": human}[kind]
            if kind == "claude":
                if row["status"] == "planned":  # queued and later rows already have their files
                    target.setdefault(row["repo"], []).append(f"`{p['id']}`: {fill(text, row['repo'])}")
            else:
                note = f" ({row['notes']})" if row["notes"] and kind == "approve" else ""
                target.setdefault(p["id"], []).append((row["repo"], fill(text, row["repo"]) + note,
                                                       fill(text, "<o>/<r>") != text or bool(note)))

    def flag(pid):
        v = by_id[pid]["verified"]
        return " (re-check the live page first: unverified row)" if v == "no" else ""

    n_repos = len({row["repo"] for row in open_rows})
    out = [f"# Queue, {today}", "",
           f"{len(open_rows)} open listings across {n_repos} repos. New this run: {len(added)}. "
           f"No longer eligible: {len(gone)}.", "",
           "Run each platform with `/visibility:register <platform-id> --all` (platform-first: one sign-in, every repo).",
           ""]
    if added:
        out += ["## New this run", ""] + [f"- `{r['repo']}` -> `{r['platform']}`" for r in added] + [""]
    if gone:
        out += ["## No longer eligible", ""] + [f"- `{r['repo']}` -> `{r['platform']}`" for r in gone] + [""]
    out += ["## 1. Claude prepares (no approval needed)", ""]
    for repo, steps in claude.items():
        out += [f"### {repo}", ""] + [f"- [ ] {s}" for s in steps] + [""]
    out += ["## 2. Needs your yes (one yes per command; grouped by platform)", ""]
    for pid, items in sorted(approve.items(), key=lambda kv: -len({r for r, _, _ in kv[1]})):
        out += [f"### `{pid}` {by_id[pid]['name']}{flag(pid)}", ""] + [f"- [ ] {repo}: {s}" for repo, s, _ in items] + [""]
    out += ["## 3. Only you (sign-ins, forms, payouts; one sitting per platform)", ""]
    for pid, items in sorted(human.items(), key=lambda kv: -len({r for r, _, _ in kv[1]})):
        repos = sorted({r for r, _, _ in items}, key=lambda r: prio.get(r, 9))
        out += [f"### `{pid}` {by_id[pid]['name']}: {len(repos)} repo(s){flag(pid)}", "",
                f"Open {by_id[pid]['submit']}. Repos: " + ", ".join(f"https://github.com/{r}" for r in repos), ""]
        seen = set()
        for repo, s, per_repo in items:
            if per_repo:
                out.append(f"- [ ] {repo}: {s}")
            elif s not in seen:  # a step with no repo in it (the sign-in) is one task for every repo
                seen.add(s)
                out.append(f"- [ ] {s}")
        out.append("")
    if owned:
        out += ["## Owned by another skill", ""] + [f"- {see}: {', '.join(sorted(set(rs)))}" for see, rs in owned.items()]
    return "\n".join(out).rstrip() + "\n"


# ---------- report: verify listings, collect metrics ----------

def http_get(url, headers=None, timeout=15):
    """(status, body). Network errors are status 0; never raises."""
    req = urllib.request.Request(url, headers={"User-Agent": "visibility-factory", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(2_000_000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (OSError, ValueError):
        return 0, ""


def link_rel(html, repo):
    """rel tokens of the first anchor in html pointing at the repo (or its homepage left to the caller)."""
    for m in re.finditer(r"<a\b[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(r"""href=["'][^"']*github\.com/""" + re.escape(repo) + r"""(?:[/"'#?]|\.git)""", tag, re.I):
            rel = re.search(r"""rel=["']([^"']*)["']""", tag, re.I)
            return rel.group(1).strip() if rel else "dofollow (no rel)"
    return ""


def package_names(path):
    """(npm name, PyPI name) published from the repo root, if any."""
    npm = pypi = ""
    try:
        pkg = json.loads(scan.read(os.path.join(path, "package.json")) or "{}")
        if not pkg.get("private"):
            npm = pkg.get("name", "")
    except ValueError:
        pass
    m = re.search(r"^\[project\][^\[]*?^name\s*=\s*[\"']([^\"']+)", scan.read(os.path.join(path, "pyproject.toml")), re.M | re.S)
    if m:
        pypi = m.group(1)
    return npm, pypi


def metrics(repo, path, get=http_get, token=None):
    """{metric: value} for one repo. Traffic referrers need a token with push access to the repo."""
    out = {}
    gh = {"Accept": "application/vnd.github+json", **({"Authorization": f"Bearer {token}"} if token else {})}
    status, body = get(f"https://api.github.com/repos/{repo}", gh)
    if status == 200:
        d = json.loads(body)
        out["stars"], out["forks"] = d.get("stargazers_count", 0), d.get("forks_count", 0)
    if token:
        status, body = get(f"https://api.github.com/repos/{repo}/traffic/views", gh)
        if status == 200:
            out["views_14d"] = json.loads(body).get("uniques", 0)
        status, body = get(f"https://api.github.com/repos/{repo}/traffic/popular/referrers", gh)
        if status == 200:
            for ref in json.loads(body):
                out[f"referrer:{ref['referrer']}"] = ref.get("uniques", 0)
    npm, pypi = package_names(path)
    if npm:
        status, body = get(f"https://api.npmjs.org/downloads/point/last-week/{npm}")
        if status == 200:
            out["npm_week"] = json.loads(body).get("downloads", 0)
    if pypi:
        status, body = get(f"https://pypistats.org/api/packages/{pypi.lower()}/recent")
        if status == 200:
            out["pypi_week"] = json.loads(body).get("data", {}).get("last_week", 0)
    return out


def verify(ledger, get=http_get, today=""):
    """Re-open every live or submitted listing with a URL; record the link's rel or mark it missing."""
    changed = []
    for row in ledger:
        if row["status"] not in ("live", "submitted") or not row["listing_url"]:
            continue
        status, html = get(row["listing_url"])
        if status == 200:
            rel = link_rel(html, row["repo"])
            before = (row["status"], row["link_rel"])
            row["status"], row["link_rel"] = "live", rel or "no link to the repo found"
            if (row["status"], row["link_rel"]) != before:
                row["date"] = today
                changed.append(row)
        elif status in (404, 410) and row["status"] == "live":
            row["status"], row["notes"], row["date"] = "rejected", f"listing returned {status} on {today}", today
            changed.append(row)
    return changed


def report(pf, catalog, ledger, history, today, get=http_get, token=None):
    """Markdown report plus the new METRICS.csv rows."""
    changed = verify(ledger, get, today)
    prev = {}
    for m in history:  # latest earlier value per (repo, metric)
        if m["date"] < today:
            prev[(m["repo"], m["metric"])] = m["value"]
    rows, table = [], []
    domains = {}
    for row in ledger:
        if row["listing_url"]:
            host = re.sub(r"^www\.", "", urllib.parse.urlparse(row["listing_url"]).netloc)
            domains.setdefault(row["repo"], {})[host] = row["platform"]
    for r in pf["repos"]:
        if not r["enabled"]:
            continue
        m = metrics(r["repo"], r["path"], get, token)
        for k, v in m.items():
            rows.append({"date": today, "repo": r["repo"], "metric": k, "value": str(v)})

        def cell(k):
            if k not in m:
                return "-"
            p = prev.get((r["repo"], k))
            return f"{m[k]}" + (f" ({int(m[k]) - int(p):+d})" if p not in (None, "") else "")
        live = sum(1 for x in ledger if x["repo"] == r["repo"] and x["status"] == "live")
        refs = sorted(((k.split(":", 1)[1], v) for k, v in m.items() if k.startswith("referrer:")), key=lambda kv: -kv[1])
        attributed = [f"{host}{' = ' + domains[r['repo']][host] if host in domains.get(r['repo'], {}) else ''} {v}"
                      for host, v in refs[:3]]
        table.append(f"| {r['repo']} | {live} | {cell('stars')} | {cell('views_14d')} | {cell('npm_week')} "
                     f"| {cell('pypi_week')} | {'; '.join(attributed) or '-'} |")
    counts = {s: sum(1 for x in ledger if x["status"] == s) for s in STATUSES}
    out = [f"# Distribution report, {today}", "",
           " · ".join(f"{s}: {n}" for s, n in counts.items() if n), "",
           "| Repo | Live listings | Stars | Unique views 14d | npm/week | PyPI/week | Top referrers (= listing) |",
           "|---|---|---|---|---|---|---|"] + table
    if not token:
        out += ["", "Views and referrers need `GITHUB_TOKEN` with push access to each repo; without it they show `-`."]
    if changed:
        out += ["", "## Listings that changed", ""] + [
            f"- `{c['repo']}` on `{c['platform']}`: {c['status']}, link rel: {c['link_rel'] or '-'} {c['notes']}".rstrip()
            for c in changed]
    stale = [x for x in ledger if x["status"] == "live" and not x["listing_url"]]
    if stale:
        out += ["", f"{len(stale)} live row(s) have no listing_url, so they cannot be re-checked."]
    return "\n".join(out) + "\n", rows


# ---------- init ----------

def init(control, paths):
    repos = []
    for p in paths:
        try:
            origin = subprocess.run(["git", "-C", p, "remote", "get-url", "origin"], capture_output=True, text=True,
                                    timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            origin = ""
        m = re.search(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$", origin)
        if not m:
            sys.stderr.write(f"skip {p}: no github.com origin\n")
            continue
        repos.append({"repo": m[1], "path": os.path.relpath(os.path.abspath(p), os.path.abspath(control)),
                      "priority": 3, "enabled": True, "character": "", "have": [], "skip": [], "notes": ""})
    os.makedirs(control, exist_ok=True)
    target = os.path.join(control, "portfolio.json")
    if os.path.exists(target):
        sys.exit(f"{target} exists; edit it instead")
    with open(target, "w", encoding="utf-8") as f:
        json.dump({"repos": repos}, f, indent=2)
        f.write("\n")
    print(f"wrote {target} with {len(repos)} repos; set priority, character, have and skip for each")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("command", choices=["init", "plan", "report"])
    ap.add_argument("control")
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--offline", action="store_true", help="plan without checking package names on npm and PyPI")
    a = ap.parse_args()
    if a.command == "init":
        return init(a.control, a.paths)
    pf, catalog = load_portfolio(a.control), scan.load_catalog()
    ledger_path = os.path.join(a.control, "LEDGER.csv")
    ledger = read_csv(ledger_path, LEDGER_COLS)
    if a.command == "plan":
        ledger, added, gone = plan(pf, catalog, ledger, a.date, get=None if a.offline else http_get)
        write_csv(ledger_path, LEDGER_COLS, ledger)
        with open(os.path.join(a.control, "QUEUE.md"), "w", encoding="utf-8") as f:
            f.write(queue(pf, catalog, ledger, added, gone, a.date))
        print(f"{len(added)} new, {len(gone)} no longer eligible; wrote QUEUE.md and LEDGER.csv")
    else:
        mpath = os.path.join(a.control, "METRICS.csv")
        md, rows = report(pf, catalog, ledger, read_csv(mpath, METRIC_COLS), a.date, token=os.environ.get("GITHUB_TOKEN"))
        write_csv(ledger_path, LEDGER_COLS, ledger)
        write_csv(mpath, METRIC_COLS, read_csv(mpath, METRIC_COLS) + rows)
        os.makedirs(os.path.join(a.control, "reports"), exist_ok=True)
        with open(os.path.join(a.control, "reports", f"{a.date}.md"), "w", encoding="utf-8") as f:
            f.write(md)
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
