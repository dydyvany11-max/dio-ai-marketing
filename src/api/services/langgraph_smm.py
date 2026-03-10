from typing import Dict, Any

from langgraph.graph import StateGraph, END


class SmmState(Dict[str, Any]):
    pass


def _validate_input(state: SmmState) -> SmmState:
    platform = state.get("platform")
    if platform not in {"vk", "telegram"}:
        raise ValueError("platform must be 'vk' or 'telegram'")
    source_id = state.get("source_id")
    if not source_id:
        raise ValueError("source_id is required")
    return state


def _fetch_audience_stub(state: SmmState) -> SmmState:
    # TODO: integrate VK/Telegram API here
    state["raw_audience"] = {
        "members": 0,
        "activity": [],
        "geo": [],
        "age": [],
        "interests": [],
    }
    return state


def _cluster_audience_stub(state: SmmState) -> SmmState:
    # TODO: replace with real clustering
    state["clusters"] = []
    return state


def _find_competitors_stub(state: SmmState) -> SmmState:
    # TODO: replace with actual competitor detection
    state["competitors"] = []
    return state


def _build_persona_stub(state: SmmState) -> SmmState:
    state["persona"] = {
        "summary": "MVP placeholder persona",
        "segments": [],
    }
    return state


def _summarize(state: SmmState) -> SmmState:
    state["summary"] = {
        "platform": state["platform"],
        "source_id": state["source_id"],
        "clusters": state.get("clusters", []),
        "competitors": state.get("competitors", []),
        "persona": state.get("persona", {}),
    }
    return state


_graph = StateGraph(SmmState)
_graph.add_node("validate", _validate_input)
_graph.add_node("fetch_audience", _fetch_audience_stub)
_graph.add_node("cluster", _cluster_audience_stub)
_graph.add_node("competitors", _find_competitors_stub)
_graph.add_node("persona", _build_persona_stub)
_graph.add_node("summarize", _summarize)

_graph.set_entry_point("validate")
_graph.add_edge("validate", "fetch_audience")
_graph.add_edge("fetch_audience", "cluster")
_graph.add_edge("cluster", "competitors")
_graph.add_edge("competitors", "persona")
_graph.add_edge("persona", "summarize")
_graph.add_edge("summarize", END)

_compiled = _graph.compile()


def run_audience_graph(platform: str, source_id: str) -> Dict[str, Any]:
    state: SmmState = {"platform": platform, "source_id": source_id}
    result = _compiled.invoke(state)
    return {
        "summary": result.get("summary", {}),
        "raw_audience": result.get("raw_audience", {}),
    }

