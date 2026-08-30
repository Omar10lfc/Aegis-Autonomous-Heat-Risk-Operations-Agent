"""Synthesizer: cited markdown memo. LLM polish with template fallback."""

from __future__ import annotations

import json
from typing import Any

from langsmith import traceable
from pydantic import BaseModel

from app.agent.llm import LLMError, complete_json
from app.config import Settings
from app.models.schemas import TaskPlan
from app.tools.redact import redact_mapping


class MemoDraft(BaseModel):
    markdown: str


SYSTEM = (
    "Write a short ops memo in markdown. Rank sites. Cite activity_id and endpoint for every claim. "
    "No API keys. JSON {\"markdown\": \"...\"} only."
)


def template_memo(plan: TaskPlan, analysis: dict[str, Any], llm_model: str) -> str:
    layer = (analysis.get("layer") or "snapshot").capitalize()
    framing = plan.client_framing.capitalize()
    lines = [
        f"# Aegis Heat-Risk Operations Memo ({framing})",
        "",
        f"**Brief:** {plan.brief}",
        f"**Analysis Layer:** {layer} (FortyGuard Temperature API)",
        "",
        "## Ranked Sites",
    ]
    for i, row in enumerate(analysis.get("ranked_sites") or [], start=1):
        metric = (row.get("metric") or "value").replace("_", " ")
        label = row.get("label") or "site"
        pretty_label = label.replace("phx_", "Phoenix ").replace("_", " ").title()
        max_val = row.get("max")
        mean_val = row.get("mean")
        units = row.get("units") or "hr"
        if units == "hour":
            units = "hr"
        elif units == "celsius":
            units = "°C"
        lines.append(
            f"{i}. **{pretty_label}** — {max_val} {units} {metric} (mean: {mean_val} {units})"
        )
    hottest = analysis.get("hottest") or {}
    if hottest:
        metric = (hottest.get("metric") or "value").replace("_", " ")
        label = hottest.get("label") or "site"
        pretty_hottest = label.replace("phx_", "Phoenix ").replace("_", " ").title()
        units = hottest.get("units") or "hr"
        if units == "hour":
            units = "hr"
        elif units == "celsius":
            units = "°C"
        lines += [
            "",
            "## Operational Recommendation",
            f"Prioritize heat mitigation and operational restaging away from **{pretty_hottest}** first; it registered the highest {analysis.get('layer', 'heat')} risk ({hottest.get('max')} {units} {metric}).",
        ]
    if analysis.get("validation_errors"):
        lines += ["", "## Validation", *[f"- {e}" for e in analysis["validation_errors"]]]
    return "\n".join(lines) + "\n"


@traceable(name="synthesizer", process_inputs=redact_mapping, process_outputs=redact_mapping)
async def synthesize(
    plan: TaskPlan,
    analysis: dict[str, Any],
    settings: Settings,
    llm_model: str,
) -> str:
    fallback = template_memo(plan, analysis, llm_model)
    if settings.aegis_llm_mode == "heuristic" or not settings.aegis_synth_llm or not settings.llm_available:
        return fallback
    try:
        draft, _model = await complete_json(
            settings,
            system=SYSTEM,
            user=(
                f"Plan rationale: {plan.rationale}\n"
                f"Analysis JSON: {json.dumps(analysis, default=str)}\n"
                f"Template:\n{fallback}"
            ),
            schema=MemoDraft,
        )
        if "activity_id" not in draft.markdown and analysis.get("citations"):
            return fallback
        return draft.markdown
    except LLMError:
        return fallback
