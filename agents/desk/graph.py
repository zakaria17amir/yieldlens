from collections.abc import Awaitable, Callable
from datetime import datetime

from langgraph.graph import END, START, StateGraph

from desk.config import Settings
from desk.executor import ExecutorProtocol
from desk.nodes.advocates import make_advocate
from desk.nodes.executor import make_executor_node
from desk.nodes.reporter import make_reporter_node
from desk.nodes.risk import make_risk_officer, prepare_rebuttal, route_after_risk
from desk.nodes.scouts import make_gmx_scout, make_pendle_scout
from desk.nodes.stats import route_after_stats, stats_node
from desk.schemas import MarketSnapshot, PendleSnapshot
from desk.state import DeskState


def build_graph(
    *,
    llm_small,
    llm_large,
    fetch_gmx: Callable[[str, Settings, datetime], Awaitable[MarketSnapshot]],
    fetch_pendle: Callable[[Settings, datetime], Awaitable[PendleSnapshot]],
    executor: ExecutorProtocol,
    now: Callable[[], datetime],
    settings: Settings,
):
    graph = StateGraph(DeskState)
    graph.add_node("gmx_scout", make_gmx_scout(fetch_gmx, settings, now))
    graph.add_node("pendle_scout", make_pendle_scout(fetch_pendle, settings, now))
    graph.add_node("stats", stats_node)
    graph.add_node("fixed_advocate", make_advocate("fixed", llm_large))
    graph.add_node("float_advocate", make_advocate("floating", llm_large))
    graph.add_node("risk_officer", make_risk_officer(llm_large, settings, now))
    graph.add_node("prepare_rebuttal", prepare_rebuttal)
    graph.add_node("executor", make_executor_node(executor, now))
    graph.add_node("reporter", make_reporter_node(settings, now))

    graph.add_edge(START, "gmx_scout")
    graph.add_edge(START, "pendle_scout")
    graph.add_edge(["gmx_scout", "pendle_scout"], "stats")
    graph.add_conditional_edges(
        "stats", route_after_stats, ["fixed_advocate", "float_advocate", "reporter"]
    )
    graph.add_edge(["fixed_advocate", "float_advocate"], "risk_officer")
    graph.add_conditional_edges(
        "risk_officer",
        route_after_risk,
        {"advocates": "prepare_rebuttal", "executor": "executor"},
    )
    graph.add_edge("prepare_rebuttal", "fixed_advocate")
    graph.add_edge("prepare_rebuttal", "float_advocate")
    graph.add_edge("executor", "reporter")
    graph.add_edge("reporter", END)
    return graph.compile()
