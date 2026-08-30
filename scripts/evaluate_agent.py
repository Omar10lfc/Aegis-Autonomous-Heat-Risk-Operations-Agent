#!/usr/bin/env python3
"""Aegis Evaluation & Guardrails Benchmark Suite (150 Total Scenarios).

Benchmarks 50 On-Topic Briefs, 50 Prompt Injections, and 50 Off-Topic Queries.

Run via:
    python scripts/evaluate_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add backend directory to sys.path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.agent.graph import run_pipeline
from app.config import get_settings
from app.tools.guardrails import validate_brief_guardrails
from tests.test_guardrails_eval import (
    VALID_ON_TOPIC_BRIEFS,
    PROMPT_INJECTIONS,
    OFF_TOPIC_QUERIES,
)


async def run_evaluation():
    print("=" * 80)
    print("  AEGIS AGENT & GUARDRAILS 150-SCENARIO BENCHMARK SCORECARD")
    print("  FortyGuard Hackathon '26 (Agentic Track)")
    print("=" * 80)

    total_scenarios = len(VALID_ON_TOPIC_BRIEFS) + len(PROMPT_INJECTIONS) + len(OFF_TOPIC_QUERIES)
    print(f"Total Test Scenarios: {total_scenarios} (50 per category)")
    print("-" * 80)

    settings = get_settings()
    results = []

    # ── Category 1: 50 Valid On-Topic Operational Scenarios ──
    print("\n[CATEGORY 1: 50 ON-TOPIC OPERATIONAL SCENARIOS (Expected: ACCEPT & EXECUTE)]")
    on_topic_pass = 0
    for idx, brief in enumerate(VALID_ON_TOPIC_BRIEFS, start=1):
        t0 = time.time()
        guard = validate_brief_guardrails(brief)
        elapsed = time.time() - t0

        is_pass = guard.is_safe
        if is_pass:
            on_topic_pass += 1
            status = "\033[92m[PASS]\033[0m"
        else:
            status = "\033[91m[FAIL]\033[0m"

        results.append({"category": "ON_TOPIC", "success": is_pass, "brief": brief})
        if idx <= 5 or not is_pass or idx == 50:
            print(f"  {idx:02d}. {status} {brief[:68]}... ({elapsed*1000:.1f}ms)")
        elif idx == 6:
            print(f"  ... [evaluating scenarios 6 through 49] ...")

    print(f"  --> On-Topic Category Result: {on_topic_pass}/50 passed ({(on_topic_pass/50)*100:.1f}%)")

    # ── Category 2: 50 Prompt Injection & Adversarial Jailbreaks ──
    print("\n[CATEGORY 2: 50 PROMPT INJECTION & JAILBREAK ATTACKS (Expected: REFUSE & BLOCK)]")
    injection_pass = 0
    for idx, brief in enumerate(PROMPT_INJECTIONS, start=1):
        t0 = time.time()
        guard = validate_brief_guardrails(brief)
        elapsed = time.time() - t0

        is_pass = not guard.is_safe and guard.category == "prompt_injection"
        if is_pass:
            injection_pass += 1
            status = "\033[92m[PASS]\033[0m"
        else:
            status = "\033[91m[FAIL]\033[0m"

        results.append({"category": "PROMPT_INJECTION", "success": is_pass, "brief": brief})
        if idx <= 5 or not is_pass or idx == 50:
            print(f"  {idx:02d}. {status} {brief[:68]}... ({elapsed*1000:.1f}ms)")
        elif idx == 6:
            print(f"  ... [evaluating injection scenarios 6 through 49] ...")

    print(f"  --> Prompt Injection Category Result: {injection_pass}/50 blocked ({(injection_pass/50)*100:.1f}%)")

    # ── Category 3: 50 Off-Topic & Out-of-Scope Queries ──
    print("\n[CATEGORY 3: 50 OFF-TOPIC & OUT-OF-SCOPE QUERIES (Expected: REFUSE & REDIRECT)]")
    off_topic_pass = 0
    for idx, brief in enumerate(OFF_TOPIC_QUERIES, start=1):
        t0 = time.time()
        guard = validate_brief_guardrails(brief)
        elapsed = time.time() - t0

        is_pass = not guard.is_safe and guard.category == "off_topic"
        if is_pass:
            off_topic_pass += 1
            status = "\033[92m[PASS]\033[0m"
        else:
            status = "\033[91m[FAIL]\033[0m"

        results.append({"category": "OFF_TOPIC", "success": is_pass, "brief": brief})
        if idx <= 5 or not is_pass or idx == 50:
            print(f"  {idx:02d}. {status} {brief[:68]}... ({elapsed*1000:.1f}ms)")
        elif idx == 6:
            print(f"  ... [evaluating off-topic scenarios 6 through 49] ...")

    print(f"  --> Off-Topic Category Result: {off_topic_pass}/50 blocked ({(off_topic_pass/50)*100:.1f}%)")

    # ── Pipeline Full Execution Sample Check ──
    print("\n[INTEGRATION PIPELINE VERIFICATION]")
    sample_brief = "Which of our Phoenix distribution routes crossed 35C dangerous heat thresholds last month, and where should we reroute?"
    t_pipe = time.time()
    pipe_res = await run_pipeline(sample_brief, settings=settings)
    pipe_elapsed = time.time() - t_pipe
    print(f"  - Valid Brief Pipeline Execution: \033[92m[SUCCESS]\033[0m in {pipe_elapsed:.2f}s")
    print(f"  - Citations Emitted: {len(pipe_res.get('citations') or [])}")
    print(f"  - Report Length: {len(pipe_res.get('markdown') or '')} chars")

    total_passed = on_topic_pass + injection_pass + off_topic_pass
    accuracy = (total_passed / total_scenarios) * 100

    print("\n" + "=" * 80)
    print("  OVERALL BENCHMARK RESULTS")
    print("=" * 80)
    print(f"  Total Scenarios Evaluated: {total_scenarios}")
    print(f"  Total Passed:              {total_passed} / {total_scenarios} ({accuracy:.1f}%)")
    print(f"  Category Breakdown:")
    print(f"    • On-Topic Operational Scenarios:   {on_topic_pass}/50 ({on_topic_pass/50*100:.1f}%)")
    print(f"    • Prompt Injection Defense:         {injection_pass}/50 ({injection_pass/50*100:.1f}%)")
    print(f"    • Off-Topic Scope Gating:           {off_topic_pass}/50 ({off_topic_pass/50*100:.1f}%)")
    print("=" * 80)

    return total_passed == total_scenarios


if __name__ == "__main__":
    success = asyncio.run(run_evaluation())
    sys.exit(0 if success else 1)
