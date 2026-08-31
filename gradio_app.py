#!/usr/bin/env python3
"""Aegis — Hugging Face Spaces Gradio Application.

Allows one-click deployment on Hugging Face Spaces (Free Tier with Gradio SDK).
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

import gradio as gr
from app.agent.graph import run_pipeline
from app.config import get_settings
from app.tools.guardrails import validate_brief_guardrails

EXAMPLE_BRIEF = (
    "Which of our Phoenix distribution routes crossed dangerous heat thresholds "
    "last month, and where should we reroute?"
)


async def analyze_heat_risk(brief: str):
    if not brief or len(brief.strip()) < 8:
        return (
            "⚠️ **Error**: Please provide a detailed brief of at least 8 characters.",
            [],
            "N/A",
            "N/A",
            "N/A",
        )

    # 1. Guardrail filter check
    guard = validate_brief_guardrails(brief)
    if not guard.is_safe:
        notice = (
            f"### 🛡️ Aegis Safety Guardrail Refusal ({guard.category})\n\n"
            f"> **Reason:** {guard.reason}\n\n"
            f"*Aegis operates strictly for street-level temperature and heat-risk intelligence.*"
        )
        return notice, [], "Blocked by Guardrails", "N/A", "N/A"

    # 2. Run Pipeline
    settings = get_settings()
    res = await run_pipeline(brief, settings=settings)

    memo_md = res.get("markdown", "No memo generated.")
    citations = res.get("citations", [])

    # Format citations as table data
    table_rows = []
    for c in citations:
        table_rows.append([
            c.get("label", "Unknown").replace("_", " ").title(),
            f"{c.get('field', '').replace('_', ' ').title()}: {c.get('value', '—')} {c.get('units', '')}",
            c.get("endpoint", "—"),
            c.get("activity_id", "—")[:8] if c.get("activity_id") else "—",
        ])

    trace_url = res.get("langsmith_url") or "LangSmith Traced"
    model_used = res.get("llm_model") or "Aegis Hybrid Engine"
    mode = res.get("fortyguard_mode") or "cached"

    return memo_md, table_rows, trace_url, model_used, mode


def run_sync(brief: str):
    return asyncio.run(analyze_heat_risk(brief))


# ── Gradio UI ──
custom_css = """
body { background-color: #101312; color: #e8ebe7; }
.gradio-container { max-width: 1200px !important; }
"""

with gr.Blocks(title="Aegis — Heat Risk Intelligence", theme=gr.themes.Monochrome()) as demo:
    gr.Markdown(
        """
        # 🛡️ Aegis — Autonomous Heat-Risk Operations Agent
        ### Street-Level Heat Risk Intelligence · Powered by FortyGuard Temperature API
        *FortyGuard Hackathon '26 (Agentic Track)*
        """
    )

    with gr.Row():
        with gr.Column(scale=5):
            brief_input = gr.Textbox(
                label="Operations Brief (Plain English)",
                placeholder=EXAMPLE_BRIEF,
                lines=4,
                value=EXAMPLE_BRIEF,
            )
            with gr.Row():
                submit_btn = gr.Button("🚀 Run Agent", variant="primary")
                example_btn = gr.Button("📋 Reset to Example", variant="secondary")

            with gr.Row():
                model_box = gr.Textbox(label="Planner Model", interactive=False)
                mode_box = gr.Textbox(label="Data Mode", interactive=False)
                trace_box = gr.Textbox(label="Observability Trace", interactive=False)

        with gr.Column(scale=7):
            memo_output = gr.Markdown(label="Executive Operations Memo")

    gr.Markdown("### 📊 Verified Citations & Provenance Audit Trail")
    citations_table = gr.Dataframe(
        headers=["Site", "Metric & Reading", "Source Endpoint", "Activity ID"],
        datatype=["str", "str", "str", "str"],
        interactive=False,
    )

    # Event handlers
    submit_btn.click(
        fn=run_sync,
        inputs=[brief_input],
        outputs=[memo_output, citations_table, trace_box, model_box, mode_box],
    )
    example_btn.click(
        fn=lambda: EXAMPLE_BRIEF,
        inputs=[],
        outputs=[brief_input],
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
