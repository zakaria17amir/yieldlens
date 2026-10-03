import asyncio
import csv
import json
from pathlib import Path

from desk.evals_support import fake_llm_from_cache, load_golden
from evals.run_evals import CACHE, GOLDEN, evaluate, main, passes
from replay.replay import run

GOLDEN_FILES = sorted(GOLDEN.glob("*.json"))


def test_golden_files_validate():
    assert len(GOLDEN_FILES) == 23
    names = {p.stem for p in GOLDEN_FILES}
    assert {"stale_gmx", "expiring_market", "expired_fallback"} <= names
    assert sum(n.startswith("window_") for n in names) == 20
    for path in GOLDEN_FILES:
        case = load_golden(path)
        lo, hi = case["expected_band"]
        assert 0 <= lo <= hi <= 10_000
        assert (CACHE / f"{path.stem}.json").exists()


def test_cache_files_are_labelled_and_load():
    for path in CACHE.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["recorded_with"] in {"rule", "live"}
        fake_llm_from_cache(payload)


def test_run_evals_cached_passes_thresholds():
    results = asyncio.run(evaluate("cached"))
    assert results["cases"] == 23
    assert passes(results)
    assert results["veto_accuracy"] == 1.0
    assert results["citation_validity_rate"] == 1.0


def test_run_evals_main_writes_results(tmp_path: Path):
    out = tmp_path / "latest.json"
    assert main(["--mode", "cached", "--out", str(out)]) == 0
    assert {"in_band_rate", "veto_accuracy", "citation_validity_rate", "mean_tokens", "mean_latency_s"} <= set(
        json.loads(out.read_text(encoding="utf-8"))
    )


def test_replay_rule_only_produces_csv_and_png(tmp_path: Path):
    rows, (csv_path, png_path) = run(
        window=90, cadence_days=1, start_split=5000, rule_only=True, out_dir=tmp_path
    )
    assert png_path.stat().st_size > 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["date", "split_bps", "desk_value", "always_fixed", "always_floating"]
        loaded = list(reader)
    assert len(loaded) == len(rows) == 90
    assert float(loaded[0]["desk_value"]) == 100.0
    assert all(0 <= int(r["split_bps"]) <= 10_000 for r in loaded)
