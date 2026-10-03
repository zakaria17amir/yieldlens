import json
import logging
from collections.abc import Callable
from datetime import datetime

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from desk.config import Settings
from desk.nodes.advocates import data_json
from desk.prompts import load_prompt
from desk.schemas import DeskAborted, Verdict
from desk.state import DeskState
from desk.tools.risk import enforce, expiry_blocks_fixed, freshness_errors


logger = logging.getLogger(__name__)


def _drop_out_of_range_objections(verdict: Verdict, state: DeskState) -> Verdict:
    sizes = {
        "fixed": len(state["fixed_case"].arguments),
        "floating": len(state["float_case"].arguments),
    }
    kept = [o for o in verdict.objections if 0 <= o.argument_idx < sizes[o.to]]
    if len(kept) != len(verdict.objections):
        logger.warning("dropped %d out-of-range objections", len(verdict.objections) - len(kept))
        return verdict.model_copy(update={"objections": kept})
    return verdict


def make_risk_officer(llm, settings: Settings, now: Callable[[], datetime]):
    structured = llm.with_structured_output(Verdict)
    template = load_prompt("risk")

    async def risk_officer(state: DeskState) -> dict:
        moment = now()
        freshness = freshness_errors(state["gmx"], state["pendle"], moment, settings.max_age_hours)
        blocked = expiry_blocks_fixed(state["pendle"], moment, settings.min_days_to_expiry)
        cases = {
            "fixed": state["fixed_case"].model_dump(mode="json"),
            "floating": state["float_case"].model_dump(mode="json"),
        }
        system = template.format(
            freshness_errors=json.dumps(freshness),
            expiry_blocked=str(blocked).lower(),
            cases_json=json.dumps(cases, sort_keys=True),
            data_json=data_json(state),
        )
        messages = [SystemMessage(content=system), HumanMessage(content="Give your verdict.")]
        for _ in range(2):
            try:
                verdict = await structured.ainvoke(messages)
            except (ValidationError, OutputParserException) as exc:
                logger.warning("risk_officer output unparseable: %s", type(exc).__name__)
                continue
            verdict = _drop_out_of_range_objections(verdict, state)
            return {"verdict": enforce(verdict, freshness, blocked)}
        raise DeskAborted("risk_officer: unparseable output")

    return risk_officer


def route_after_risk(state: DeskState) -> str:
    if state["verdict"].needs_rebuttal and state.get("rebuttal_round", 0) == 0:
        return "advocates"
    return "executor"


async def prepare_rebuttal(state: DeskState) -> dict:
    objections = state["verdict"].objections
    return {
        "rebuttal_round": 1,
        "objections_for_fixed": [o for o in objections if o.to == "fixed"],
        "objections_for_float": [o for o in objections if o.to == "floating"],
    }
