from typing import Any, Literal

from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from desk.config import Settings


def make_llm(tier: Literal["small", "large"], settings: Settings) -> BaseChatModel:
    model = settings.model_small if tier == "small" else settings.model_large
    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
        return ChatOpenAI(model=model, temperature=0, api_key=key)
    from langchain_anthropic import ChatAnthropic

    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    return ChatAnthropic(model=model, temperature=0, api_key=key)


class _FakeStructured:
    def __init__(self, llm: "FakeLLM", model: type[BaseModel]):
        self._llm = llm
        self._model = model

    def _next(self, messages: Any) -> BaseModel:
        self._llm.calls.append((self._model, messages))
        queue = self._llm.queues.get(self._model)
        assert queue, f"FakeLLM queue empty for {self._model.__name__}"
        text = "".join(str(getattr(m, "content", m)) for m in messages)
        for i, item in enumerate(queue):
            position = getattr(item, "position", None)
            if position is None or f"the {position} advocate" in text:
                return queue.pop(i)
        raise AssertionError(f"FakeLLM has no queued {self._model.__name__} for this prompt")

    def invoke(self, messages: Any, *args: Any, **kwargs: Any) -> BaseModel:
        return self._next(messages)

    async def ainvoke(self, messages: Any, *args: Any, **kwargs: Any) -> BaseModel:
        return self._next(messages)


class FakeLLM:
    def __init__(self, queues: dict[type[BaseModel], list[BaseModel]] | None = None):
        self.queues: dict[type[BaseModel], list[BaseModel]] = queues or {}
        self.calls: list[tuple[type[BaseModel], Any]] = []

    def queue(self, *items: BaseModel) -> "FakeLLM":
        for item in items:
            self.queues.setdefault(type(item), []).append(item)
        return self

    def with_structured_output(self, model: type[BaseModel], **_: Any) -> _FakeStructured:
        return _FakeStructured(self, model)
