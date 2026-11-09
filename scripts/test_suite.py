"""Run reproducibly shuffled unittest modules in balanced CI shards, recording timings.

Each repeat is loaded anew in the same interpreter, so leaked globals are visible.
Class groups stay together to preserve unittest's class fixture lifecycle. Timings
are plain JSON, usable to rebalance later runs without a test-runner dependency.
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def modules() -> list[str]:
    """Discover test modules by filename without importing or starting any browsers."""
    return ["tests." + p.stem for p in sorted((ROOT / "tests").glob("test_*.py"))]


def partition(names: list[str], count: int, timings: dict) -> list[list[str]]:
    """Put the slowest modules first in the least loaded shard; ties are deterministic."""
    weights = {name: max(0.01, float(timings.get(name, 1))) for name in names}
    shards, totals = [[] for _ in range(count)], [0.0] * count
    for name in sorted(names, key=lambda n: (-weights[n], n)):
        shard = min(range(count), key=lambda i: (totals[i], i))
        shards[shard].append(name)
        totals[shard] += weights[name]
    return shards


def flatten(suite):
    """Yield test cases recursively, leaving the loader's error cases visible."""
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def shuffled(names: list[str], seed: int) -> unittest.TestSuite:
    """Shuffle classes and their methods, keeping each class in one contiguous group."""
    rng, groups = random.Random(seed), collections.defaultdict(list)
    for name in names:
        for test in flatten(unittest.defaultTestLoader.loadTestsFromName(name)):
            groups[type(test)].append(test)
    classes = list(groups)
    rng.shuffle(classes)
    out = unittest.TestSuite()
    for cls in classes:
        rng.shuffle(groups[cls])
        out.addTests(groups[cls])
    return out


class TimedResult(unittest.TextTestResult):
    """Record test time and failures in a machine-readable summary as well as unittest output."""

    def startTest(self, test):
        """Start the timer immediately before this test's setup."""
        self.started = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        """Accumulate by module, so a later CI run can balance the same units."""
        self.timings[type(test).__module__] += time.perf_counter() - self.started
        super().stopTest(test)


def main(argv=None) -> int:
    """Run a shard, print the seed and selected modules, and always write its summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--shard", default="1/1", help="One-based shard/count")
    parser.add_argument("--seed", type=int, default=315)
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timings", type=Path, default=ROOT / "tests" / "timings.json")
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args(argv)
    try:
        index, count = map(int, args.shard.split("/"))
        if not 1 <= index <= count or args.repeat < 1:
            raise ValueError()
    except ValueError:
        parser.error("--shard must be index/count with 1 <= index <= count; --repeat must be positive")
    history = json.loads(args.timings.read_text()) if args.timings.exists() else {}
    selected = partition(args.names or modules(), count, history)[index - 1]
    print(f"Shard {index}/{count}; seed {args.seed}; repeats {args.repeat}", flush=True)
    print("Modules: " + ", ".join(selected), flush=True)
    timings, failures, totals = collections.defaultdict(float), [], 0
    for repeat in range(args.repeat):
        print(f"Pass {repeat + 1}; seed {args.seed + repeat}", flush=True)
        TimedResult.timings = timings
        result = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult).run(shuffled(selected, args.seed + repeat))
        totals += result.testsRun
        failures.extend({"test": str(test), "traceback": trace} for test, trace in result.errors + result.failures)
    summary = {"seed": args.seed, "shard": args.shard, "repeats": args.repeat, "tests": totals,
               "failures": failures, "timings": {k: round(v / args.repeat, 3) for k, v in timings.items()}}
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
