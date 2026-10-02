"""
Usage:
  export GITHUB_TOKEN=ghp_...
  uv run --no-sync corpus-enrich
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .seeds import INCIDENTS

RESULTS = Path(__file__).resolve().parents[2] / "results"
API = "https://api.github.com"


def _repo_slug(repo: str) -> str | None:
    # seeds store repos as "langchain-ai/langgraph" etc. for GitHub rows.
    if "/" in repo and repo not in ("forum.langchain.com",):
        return repo
    return None


def fetch_issue(slug: str, number: int, token: str | None) -> tuple[dict | None, str]:
    """Return (payload, status). status in {ok, not_found, rate_limited, error}."""
    url = f"{API}/repos/{slug}/issues/{number}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "soundgate-corpus-enricher",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode()), "ok"
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, "not_found"
        if e.code in (403, 429):
            return None, "rate_limited"
        return None, f"http_{e.code}"
    except Exception as e:  # noqa: BLE001
        return None, f"error:{type(e).__name__}"


def enrich_one(rec: dict, token: str | None) -> dict:
    out = dict(rec)
    slug = _repo_slug(rec["repo"])
    if slug is None or rec["kind"] not in ("issue",) or rec["id"] is None:
        out["enrich"] = {"enrich_status": "skipped_non_github"}
        return out
    payload, status = fetch_issue(slug, int(rec["id"]), token)
    if status != "ok" or payload is None:
        out["enrich"] = {"enrich_status": status}
        return out
    live = {
        "enrich_status": "ok",
        "state": payload.get("state"),
        "created_at": payload.get("created_at"),
        "closed_at": payload.get("closed_at"),
        "author": (payload.get("user") or {}).get("login"),
        "author_association": payload.get("author_association"),
        "labels": [l.get("name") for l in payload.get("labels", [])],
        "is_pull_request": "pull_request" in payload,
        "title_live": payload.get("title"),
    }
    # Flag mismatches instead of trusting one side.
    flags = []
    if rec.get("title") and live["title_live"] and rec["title"].strip() != live["title_live"].strip():
        flags.append("title_mismatch")
    if rec.get("created") and live["created_at"] and not live["created_at"].startswith(rec["created"]):
        flags.append("date_mismatch")
    if flags:
        live["flags"] = flags
    out["enrich"] = live
    return out


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("WARNING: no GITHUB_TOKEN set; anonymous limit is 60/hr and may be "
              "exhausted on a shared IP. Set GITHUB_TOKEN for reliable enrichment.")
    out_path = RESULTS / "incidents_enriched.jsonl"
    n_ok = n_skip = n_fail = 0
    with out_path.open("w") as fh:
        for rec in INCIDENTS:
            enriched = enrich_one(rec, token)
            st = enriched["enrich"]["enrich_status"]
            if st == "ok":
                n_ok += 1
            elif st == "skipped_non_github":
                n_skip += 1
            else:
                n_fail += 1
                print(f"  {rec['repo']}#{rec['id']}: {st}")
            fh.write(json.dumps(enriched) + "\n")
            if _repo_slug(rec["repo"]) and rec["kind"] == "issue":
                time.sleep(0.2)  # be polite
    print(f"wrote {out_path.name}: {n_ok} enriched, {n_skip} non-GitHub skipped, "
          f"{n_fail} failed/rate-limited")
    if n_fail:
        print("Re-run with GITHUB_TOKEN set to complete enrichment; failed rows "
              "kept their observed fields and are marked in the 'enrich' object.")


if __name__ == "__main__":
    main()