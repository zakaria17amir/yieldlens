import pytest_asyncio

from desk.tools import http


@pytest_asyncio.fixture(autouse=True)
async def _close_http_client():
    yield
    await http.aclose()
