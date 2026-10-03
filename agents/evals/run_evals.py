"""Run the golden evals.

Modes:
  cached  replay recorded responses from evals/cache/{case}.json through a FakeLLM (CI default)
  rule    drive the graph with the deterministic RuleLLM; with --record, writes the cache
  live    real LLMs (needs an API key); with --record, writes the cache

The committed cache was recorded with `--mode rule` (recorded_with="rule") because no LLM key was
available; re-record with `--mode live --record` once a key exists.
mean_tokens is 0 outside live mode.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from desk.config import Settings
from desk.evals_support import (
    RecordingLLM,
    RuleLLM,
    cache_payload,
    fake_llm_from_cache,
    load_golden,
    run_graph_once,
)
from desk.llm import make_llm
from desk.tools.evidence import allowed_fields

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
CACHE = HERE / "cache"
RESULTS = HERE / "results" / "latest.json"
MIN_IN_BAND = 0.8
MIN_VETO_ACCURACY = 1.0


async def evaluate(mode: str, *, record: bool = False, golden_dir: Path = GOLDEN, cache_dir: Path = CACHE) -> dict:
    rows = []
    total_tokens = 0
    for path in sorted(golden_dir.glob("*.json")):
        case = load_golden(path)
        name, gmx, pendle, now = case["name"], case["gmx"], case["pendle"], case["now"]
        recorded_with = mode
        if mode == "cached":
            payload = json.loads((cache_dir / f"{name}.json").read_text(encoding="utf-8"))
            recorded_with = payload["recorded_with"]
            llm = fake_llm_from_cache(payload)
        elif mode == "rule":
            llm = RecordingLLM(RuleLLM(gmx, pendle))
        else:
            llm = RecordingLLM(make_llm("large", Settings()))

        started = time.perf_counter()
        if mode == "live":
            from langchain_core.callbacks import get_usage_metadata_callback

            with get_usage_metadata_callback() as usage:
                report = await run_graph_once(gmx, pendle, now, llm, name)
            total_tokens += sum(u.get("total_tokens", 0) for u in usage.usage_metadata.values())
        else:
            report = await run_graph_once(gmx, pendle, now, llm, name)
        latency = time.perf_counter() - started

        if record and mode != "cached":
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / f"{name}.json").write_text(
                json.dumps(cache_payload(name, mode, llm.recorded), indent=1) + "\n",
                encoding="utf-8",
                newline="\n",
            )

        allowed = allowed_fields(report.stats, report.gmx, report.pendle)
        cited = [a.evidence_field for c in (report.fixed_case, report.float_case) if c for a in c.arguments]
        lo, hi = case["expected_band"]
        target = report.verdict.target_fixed_bps
        rows.append(
            {
                "name": name,
                "target_fixed_bps": target,
                "vetoed": report.verdict.vetoed,
                "expect_veto": case["expect_veto"],
                "in_band": lo <= target <= hi,
                "citations_valid": sum(f in allowed for f in cited),
                "citations_total": len(cited),
                "latency_s": latency,
                "recorded_with": recorded_with,
            }
        )

    band_rows = [r for r in rows if not r["expect_veto"]]
    cites = sum(r["citations_total"] for r in rows)
    return {
        "mode": mode,
        "cases": len(rows),
        "in_band_rate": sum(r["in_band"] for r in band_rows) / len(band_rows),
        "veto_accuracy": sum(r["vetoed"] == r["expect_veto"] for r in rows) / len(rows),
        "citation_validity_rate": sum(r["citations_valid"] for r in rows) / cites if cites else 1.0,
        "mean_tokens": total_tokens / len(rows) if mode == "live" else 0,
        "mean_latency_s": sum(r["latency_s"] for r in rows) / len(rows),
        "recorded_with": sorted({r["recorded_with"] for r in rows}),
        "rows": rows,
    }


def passes(results: dict) -> bool:
    return results["in_band_rate"] >= MIN_IN_BAND and results["veto_accuracy"] >= MIN_VETO_ACCURACY


def print_table(results: dict) -> None:
    print(f"{'case':<20}{'target':>8}{'vetoed':>8}{'in_band':>9}{'cites':>8}")
    for r in results["rows"]:
        cites = f"{r['citations_valid']}/{r['citations_total']}"
        print(f"{r['name']:<20}{r['target_fixed_bps']:>8}{str(r['vetoed']):>8}{str(r['in_band']):>9}{cites:>8}")
    for key in ("in_band_rate", "veto_accuracy", "citation_validity_rate", "mean_tokens", "mean_latency_s"):
        print(f"{key}: {results[key]:.3f}")
    print(f"recorded_with: {results['recorded_with']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["cached", "rule", "live"], default="cached")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args(argv)
    results = asyncio.run(evaluate(args.mode, record=args.record))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=1) + "\n", encoding="utf-8", newline="\n")
    print_table(results)
    return 0 if passes(results) else 1


if __name__ == "__main__":
    sys.exit(main())
