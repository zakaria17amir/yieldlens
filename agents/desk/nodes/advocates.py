import json
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage

from desk.prompts import load_prompt
from desk.schemas import Case, DeskAborted
from desk.state import DeskState
from desk.tools.evidence import allowed_fields, invalid_citations

Position = Literal["fixed", "floating"]


def data_json(state: DeskState) -> str:
    payload = {
        "stats": state["stats"].model_dump(mode="json"),
        "gmx": state["gmx"].model_dump(mode="json", by_alias=True),
        "pendle": state["pendle"].model_dump(mode="json", exclude={"history"}),
    }
    return json.dumps(payload, sort_keys=True)


def make_advocate(position: Position, llm):
    structured = llm.with_structured_output(Case)
    template = load_prompt("advocate")
    objections_key = "objections_for_fixed" if position == "fixed" else "objections_for_float"
    case_key = "fixed_case" if position == "fixed" else "float_case"

    async def advocate(state: DeskState) -> dict:
        allowed = allowed_fields(state["stats"], state["gmx"], state["pendle"])
        rebuttal = state.get("rebuttal_round", 0) == 1
        objections = state.get(objections_key, []) if rebuttal else []
        system = template.format(
            position=position,
            allowed_fields="\n".join(sorted(allowed)),
            data_json=data_json(state),
            objections_json=json.dumps([o.model_dump() for o in objections]),
        )
        messages = [
            SystemMessage(content=system),
            HumanMessage(content=f"Make your {position} case."),
        ]
        problem = ""
        for _ in range(2):
            case = await structured.ainvoke(messages)
            if case.position != position:
                problem = f"position must be {position!r}"
            elif bad := invalid_citations(case, allowed):
                problem = f"arguments {bad} cite fields that do not exist"
            else:
                return {case_key: case}
            messages = [*messages, HumanMessage(content=f"Invalid case: {problem}. Try again.")]
        raise DeskAborted(f"{position}_advocate: {problem}")

    return advocate
