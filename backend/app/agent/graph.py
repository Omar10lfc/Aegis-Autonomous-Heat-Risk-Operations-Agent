"""LangGraph: planner → executor → analyzer → synthesizer. LangSmith from the first wiring."""

from __future__ import annotations

import os
from datetime import date
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import traceable

from app.agent.analyzer import analyze
from app.agent.executor import Executor
from app.agent.planner import plan_brief
from app.agent.synthesizer import synthesize
from app.config import Settings, get_settings
from app.models.schemas import ExecutorResult, TaskPlan
from app.tools.fortyguard_client import FortyGuardClient
from app.tools.redact import redact_mapping, redact_value


class AgentState(TypedDict, total=False):
    brief: str
    as_of: str | None
    plan: dict[str, Any]
    executor_result: dict[str, Any]
    analysis: dict[str, Any]
    markdown: str
    citations: list[dict[str, Any]]
    llm_model: str
    error: str | None
    langsmith_url: str | None
    fortyguard_mode: str
    stage: str


def configure_langsmith(settings: Settings) -> None:
    if settings.langchain_api_key:
        os.environ.setdefault("LANGCHAIN_API_KEY", settings.langchain_api_key)
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langchain_api_key)
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.tracing_endpoint()
    os.environ["LANGSMITH_ENDPOINT"] = settings.tracing_endpoint()
    os.environ["LANGCHAIN_HIDE_INPUTS"] = "false"


def _run_url() -> str | None:
    try:
        from langsmith.run_helpers import get_current_run_tree

        tree = get_current_run_tree()
        if tree is None:
            return None
        getter = getattr(tree, "get_url", None)
        if callable(getter):
            return str(getter())
        run_id = getattr(tree, "id", None)
        if run_id:
            return f"https://smith.langchain.com/public/{run_id}/r"
    except Exception:
        return None
    return None


@traceable(name="executor", process_inputs=redact_mapping, process_outputs=redact_mapping)
async def _executor_node(state: AgentState, settings: Settings) -> AgentState:
    if not state.get("plan"):
        return state
    plan = TaskPlan.model_validate(state["plan"])
    client = FortyGuardClient(settings)
    try:
        result = await Executor(client, settings).execute(plan)
    finally:
        await client.aclose()
    return {
        "executor_result": redact_value(result.model_dump()),
        "stage": "executor",
        "error": "; ".join(result.validation_errors) if result.validation_errors else state.get("error"),
    }


from app.tools.guardrails import validate_brief_guardrails


async def planner_node(state: AgentState, settings: Settings) -> AgentState:
    brief = state.get("brief", "")
    
    # ── Guardrail check: prompt injection & domain relevance ──
    guard = validate_brief_guardrails(brief)
    if not guard.is_safe:
        return {
            "stage": "guardrails",
            "error": f"Guardrail validation failed: {guard.reason}",
            "markdown": (
                f"# Aegis Safety & Operational Guardrail Notice\n\n"
                f"> **Status:** Query Refused by Guardrail Filter ({guard.category})\n\n"
                f"**Reason:** {guard.reason}\n\n"
                f"Aegis is specialized exclusively for street-level temperature analysis, "
                f"logistics heat-risk routing, and FortyGuard temperature intelligence."
            ),
            "citations": [],
            "fortyguard_mode": "cached",
            "llm_model": "guardrails",
        }

    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    plan, model = await plan_brief(brief, settings, as_of=as_of)
    return {
        "plan": redact_value(plan.model_dump()),
        "llm_model": model,
        "stage": "planner",
        "fortyguard_mode": "live" if settings.fortyguard_live else "cached",
    }


async def analyzer_node(state: AgentState) -> AgentState:
    if not state.get("plan") or not state.get("executor_result"):
        return state
    plan = TaskPlan.model_validate(state["plan"])
    executor_result = ExecutorResult.model_validate(state["executor_result"])
    analysis = analyze(plan, executor_result)
    return {
        "analysis": analysis,
        "citations": analysis.get("citations") or [],
        "stage": "analyzer",
    }


async def synthesizer_node(state: AgentState, settings: Settings) -> AgentState:
    if not state.get("plan") or not state.get("analysis"):
        return state
    plan = TaskPlan.model_validate(state["plan"])
    markdown = await synthesize(plan, state["analysis"], settings, state.get("llm_model") or "unknown")
    return {
        "markdown": markdown,
        "stage": "synthesizer",
        "langsmith_url": _run_url(),
    }


def build_graph(settings: Settings | None = None):
    settings = settings or get_settings()
    configure_langsmith(settings)

    async def _planner(state: AgentState) -> AgentState:
        return await planner_node(state, settings)

    async def _executor(state: AgentState) -> AgentState:
        return await _executor_node(state, settings)

    async def _analyzer(state: AgentState) -> AgentState:
        return await analyzer_node(state)

    async def _synthesizer(state: AgentState) -> AgentState:
        return await synthesizer_node(state, settings)

    graph = StateGraph(AgentState)
    graph.add_node("planner", _planner)
    graph.add_node("executor", _executor)
    graph.add_node("analyzer", _analyzer)
    graph.add_node("synthesizer", _synthesizer)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "analyzer")
    graph.add_edge("analyzer", "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile()


@traceable(name="aegis_pipeline", process_inputs=redact_mapping, process_outputs=redact_mapping)
async def run_pipeline(brief: str, settings: Settings | None = None, as_of: date | None = None) -> AgentState:
    settings = settings or get_settings()
    app = build_graph(settings)
    result = await app.ainvoke(
        {"brief": brief, "as_of": as_of.isoformat() if as_of else None, "stage": "queued"},
        config={
            "metadata": {
                "llm_model": settings.primary_model_label(),
                "fortyguard_mode": "live" if settings.fortyguard_live else "cached",
            },
            "tags": ["aegis", "fortyguard"],
        },
    )
    result["langsmith_url"] = result.get("langsmith_url") or _run_url()
    return result
