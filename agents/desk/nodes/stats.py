from desk.schemas import Verdict
from desk.state import DeskState
from desk.tools.stats import fix_vs_float_stats


async def stats_node(state: DeskState) -> dict:
    gmx, pendle = state.get("gmx"), state.get("pendle")
    if gmx is None or pendle is None:
        return {
            "stats": None,
            "errors": ["missing_data"],
            "verdict": Verdict(
                target_fixed_bps=0,
                vetoed=True,
                rationale="missing data",
                objections=[],
                needs_rebuttal=False,
            ),
        }
    return {"stats": fix_vs_float_stats(gmx, pendle)}


def route_after_stats(state: DeskState) -> list[str] | str:
    if "missing_data" in state.get("errors", []):
        return "reporter"
    return ["fixed_advocate", "float_advocate"]
