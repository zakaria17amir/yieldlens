import pytest
from langchain_core.callbacks import get_usage_metadata_callback

from desk.config import Settings
from desk.run import run_desk
from desk.tools.evidence import allowed_fields, invalid_citations

pytestmark = pytest.mark.live


async def test_live_desk_produces_valid_report(tmp_path):
    settings = Settings(runs_dir=str(tmp_path), simulate_live_market=True)
    with get_usage_metadata_callback() as usage:
        report = await run_desk(settings, dry_run=True)
    assert report.verdict is not None
    allowed = allowed_fields(report.stats, report.gmx, report.pendle)
    for case in (report.fixed_case, report.float_case):
        assert case is not None
        assert invalid_citations(case, allowed) == []
    total = sum(u.get("total_tokens", 0) for u in usage.usage_metadata.values())
    print(f"total tokens: {total}")
    assert total < 60_000
