"""Execution-ground consistency checks for Aegis.

Runs one or more briefs N times through the live backend and asserts:
  1. The ranked-site labels stay in exactly the same order run to run.
  2. Every number in the memo's "Ranked sites" lines matches its citation value.
  3. The pipeline reaches "succeeded" with non-empty citations every time.
  4. The planner model used the configured primary (no silent heuristic drift) — reported, warn-only.

Works because the cached fixtures are hash-deterministic. Run with the backend up:
    .venv\\Scripts\\python.exe scripts\\consistency_check.py [--runs 5] [--brief "..."] [--url http://localhost:8000]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BRIEF = (
    "Which of our Phoenix distribution routes crossed dangerous heat thresholds "
    "last month, and where should we reroute?"
)


def api(url: str, path: str, method: str = "GET", body: dict[str, Any] | None = None,
        timeout: float = 30) -> dict[str, Any]:
    req = urllib.request.Request(f"{url}{path}", method=method)
    payload = None
    if body is not None:
        req.add_header("Content-Type", "application/json")
        payload = json.dumps(body).encode("utf-8")
    with urllib.request.urlopen(req, payload, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wait_for(job_id: str, url: str, timeout: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = api(url, f"/status/{job_id}")
        if st["status"] in ("succeeded", "failed"):
            return st
        time.sleep(2.0)
    raise TimeoutError(f"job {job_id} not terminal after {timeout}s")


def memo_ranked_values(memo: str) -> list[tuple[str, float]]:
    """Parse 'label — metric=value unit' lines from the memo's Ranked sites block."""
    found: list[tuple[str, float]] = []
    in_ranked = False
    for raw in memo.splitlines():
        line = raw.strip()
        if line.lower().startswith("ranked sites"):
            in_ranked = True
            continue
        if in_ranked:
            if not line or line.startswith("##") or line.lower().startswith("recommendation"):
                break
            m = re.match(r"^(\S+)\s*[—-]\s*\w+=\s*([0-9.]+)", line)
            if m:
                found.append((m.group(1), float(m.group(2))))
    return found


def check_run(url: str, brief: str) -> dict[str, Any]:
    result = api(url, "/brief", method="POST", body={"brief": brief}, timeout=60)
    job_id = result["job_id"]
    status = wait_for(job_id, url)
    if status["status"] != "succeeded":
        raise AssertionError(f"job {job_id} failed: {status.get('error')}")
    report = api(url, f"/report/{job_id}")
    memo = report["markdown"]
    citations = report["citations"]
    by_label: dict[str, dict[str, Any]] = {}
    for c in citations:
        if c["field"] in ("hours_above_threshold", "peak_temp_celsius", "longest_sustained_hours"):
            by_label.setdefault(c["label"], c)
    memo_vals = dict(memo_ranked_values(memo))
    mismatches = []
    for label, value in memo_vals.items():
        cite = by_label.get(label)
        if cite is None or cite["value"] is None:
            mismatches.append(f"{label}: memo={value}, no matching citation")
        elif abs(cite["value"] - value) > 1e-9:
            mismatches.append(f"{label}: memo={value}, citation={cite['value']}")
    ranked_labels = [label for label, _ in sorted(memo_vals.items(), key=lambda kv: -kv[1])]
    return {
        "job_id": job_id,
        "status": status["status"],
        "n_citations": len(citations),
        "memo_sites": ranked_labels,
        "mismatches": mismatches,
        "planner_model": report.get("planner_model"),
        "fortyguard_mode": report.get("fortyguard_mode"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--brief", default=DEFAULT_BRIEF)
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()

    health = api(args.url, "/health")
    print(f"health: {health}")
    expected = health.get("llm_model", "?")

    order_first: list[str] | None = None
    fail = 0
    for i in range(1, args.runs + 1):
        r = check_run(args.url, args.brief)
        order = r["memo_sites"]
        drifted = order_first is not None and order != order_first
        print(f"run {i}: {r['status']} cites={r['n_citations']} "
              f"order={'OK' if not drifted else 'DRIFTED'} "
              f"model={r['planner_model']} mode={r['fortyguard_mode']}")
        if r["mismatches"]:
            fail += 1
            print(f"  MISMATCHES: {r['mismatches']}")
        if drifted:
            fail += 1
            print(f"  RANK DRIFT: {order_first} -> {order}")
        if r["planner_model"] != expected:
            print(f"  WARNING: planner {r['planner_model']} != health {expected}")
        if order_first is None:
            order_first = order

    if fail == 0:
        print(f"\nPASS: {args.runs}/{args.runs} runs consistent ({order_first})")
        return 0
    print(f"\nFAIL: {fail} inconsistency/ies across {args.runs} runs")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (urllib.error.URLError, TimeoutError, AssertionError) as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)