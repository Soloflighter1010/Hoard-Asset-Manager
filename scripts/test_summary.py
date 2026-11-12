"""Collect all CI shard failures and timings into one GitHub Actions summary."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    """Include missing or failed shards, so a broken setup never looks like a passing test run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--expected", type=int, required=True)
    args = parser.parse_args()
    reports = [(p.name, json.loads(p.read_text("utf-8"))) for p in sorted(args.folder.glob("*.json"))]
    failed = len(reports) != args.expected or os.environ.get("SHARDS_RESULT", "success") != "success"
    lines = ["## Hoard tests", "", "| Shard | Seed | Tests | Failures | Test time per pass |",
             "| --- | --- | --- | --- | --- |"]
    for name, report in reports:
        failures = report["failures"]
        failed = failed or bool(failures)
        duration = sum(report["timings"].values())
        lines.append(f"| {name} | {report['seed']} | {report['tests']} | {len(failures)} | {duration:.1f}s |")
    if len(reports) != args.expected:
        lines += ["", f"Only {len(reports)} of {args.expected} shards returned results. Check the setup logs."]
    for name, report in reports:
        for failure in report["failures"]:
            lines += ["", f"### {name}: {failure['test']}", "", "```text", failure["traceback"], "```"]
    text = "\n".join(lines) + "\n"
    print(text)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(text)
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
