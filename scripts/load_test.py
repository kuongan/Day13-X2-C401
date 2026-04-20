import argparse
import concurrent.futures
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
QUERIES = Path("data/sample_queries.jsonl")


@dataclass
class Result:
    status: int
    latency_ms: float
    correlation_id: str
    feature: str
    error: str | None = None


@dataclass
class Summary:
    results: list[Result] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers
    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successes(self) -> list[Result]:
        return [r for r in self.results if r.error is None and r.status < 400]

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if r.error is not None or r.status >= 400]

    def percentile(self, p: float) -> float:
        """Return the p-th percentile latency (ms) across successful requests."""
        latencies = sorted(r.latency_ms for r in self.successes)
        if not latencies:
            return 0.0
        idx = max(0, int(len(latencies) * p / 100) - 1)
        return latencies[idx]

    # ------------------------------------------------------------------ display
    def print(self, elapsed_wall: float) -> None:
        ok = len(self.successes)
        err = len(self.failures)
        latencies = [r.latency_ms for r in self.successes]

        print("\n" + "=" * 60)
        print("  LOAD TEST SUMMARY")
        print("=" * 60)
        print(f"  Total requests : {self.total}")
        print(f"  Successes      : {ok}  ({ok / self.total * 100:.1f}%)")
        print(f"  Failures       : {err}  ({err / self.total * 100:.1f}%)")
        print(f"  Wall time      : {elapsed_wall:.2f}s")
        print(f"  Throughput     : {self.total / elapsed_wall:.1f} req/s")

        if latencies:
            print()
            print(f"  Latency (ms)   :")
            print(f"    min          : {min(latencies):.1f}")
            print(f"    mean         : {statistics.mean(latencies):.1f}")
            print(f"    median (p50) : {self.percentile(50):.1f}")
            print(f"    p90          : {self.percentile(90):.1f}")
            print(f"    p95          : {self.percentile(95):.1f}")
            print(f"    p99          : {self.percentile(99):.1f}")
            print(f"    max          : {max(latencies):.1f}")

        # per-feature breakdown
        features: dict[str, list[float]] = {}
        for r in self.successes:
            features.setdefault(r.feature, []).append(r.latency_ms)
        if features:
            print()
            print(f"  Per-feature p95 (ms):")
            for feat, lats in sorted(features.items()):
                lats_sorted = sorted(lats)
                p95_idx = max(0, int(len(lats_sorted) * 0.95) - 1)
                print(f"    {feat:<28} {lats_sorted[p95_idx]:.1f}")

        # error details
        if self.failures:
            print()
            print("  Errors:")
            for r in self.failures:
                tag = r.error or f"HTTP {r.status}"
                print(f"    [{r.feature}] {tag}")

        print("=" * 60)


# --------------------------------------------------------------------------- core
def send_request(client: httpx.Client, payload: dict) -> Result:
    feature = payload.get("feature", "unknown")
    try:
        start = time.perf_counter()
        r = client.post(f"{BASE_URL}/chat", json=payload)
        latency = (time.perf_counter() - start) * 1000
        body = r.json()
        correlation_id = body.get("correlation_id", "-")
        print(
            f"[{r.status_code}] {correlation_id} | {feature} | {latency:.1f}ms"
        )
        return Result(
            status=r.status_code,
            latency_ms=latency,
            correlation_id=correlation_id,
            feature=feature,
        )
    except Exception as e:  # network / timeout / JSON decode
        print(f"[ERR] {feature} | {e}")
        return Result(status=0, latency_ms=0.0, correlation_id="-", feature=feature, error=str(e))


def load_queries(path: Path) -> list[dict]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [json.loads(l) for l in lines]


def main() -> None:
    parser = argparse.ArgumentParser(description="Load-test the /chat endpoint")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent workers")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat the query set N times")
    parser.add_argument(
        "--output", type=Path, default=None, help="Write per-request JSON results to file"
    )
    args = parser.parse_args()

    payloads = load_queries(QUERIES) * args.repeat
    if not payloads:
        print("No queries found – check data/sample_queries.jsonl")
        return

    summary = Summary()
    wall_start = time.perf_counter()

    with httpx.Client(timeout=30.0) as client:
        if args.concurrency > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
                futures = {executor.submit(send_request, client, p): p for p in payloads}
                for fut in concurrent.futures.as_completed(futures):
                    summary.results.append(fut.result())
        else:
            for payload in payloads:
                summary.results.append(send_request(client, payload))

    wall_elapsed = time.perf_counter() - wall_start
    summary.print(wall_elapsed)

    if args.output:
        args.output.write_text(
            json.dumps(
                [
                    {
                        "status": r.status,
                        "latency_ms": round(r.latency_ms, 2),
                        "correlation_id": r.correlation_id,
                        "feature": r.feature,
                        "error": r.error,
                    }
                    for r in summary.results
                ],
                indent=2,
            )
        )
        print(f"\nResults written to {args.output}")


if __name__ == "__main__":
    main()