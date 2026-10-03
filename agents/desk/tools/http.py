import asyncio
from typing import Any

import httpx


class DataUnavailable(Exception):
    """Raised with the data source name as its message."""


_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _get_client() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = httpx.AsyncClient()
        _client_loop = loop
    return _client


async def get_json(url: str, params: dict | None = None, timeout: float = 20) -> Any:
    response = await _get_client().get(url, params=params, timeout=timeout)
    response.raise_for_status()
    return response.json()
