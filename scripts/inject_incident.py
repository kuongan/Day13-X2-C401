from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
SCENARIOS = ["rag_slow", "tool_fail", "cost_spike"]
INCIDENTS_FILE = Path("data/incidents.json")

RAG_QUERIES = [
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "What is your refund policy?"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "Explain monitoring and observability"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "summary", "message": "Summarize the logging policy"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "What about policy and refund?"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "Help me with monitoring policy"},
]

COST_QUERIES = [
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "Tell me about refunds"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "summary", "message": "Summarize everything"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "Explain policy"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "What is monitoring?"},
    {"user_id": "u_atk", "session_id": "s_atk", "feature": "qa", "message": "Describe the refund policy in detail"},
]


def _load_descriptions() -> dict[str, str]:
    if INCIDENTS_FILE.exists():
        return json.loads(INCIDENTS_FILE.read_text(encoding="utf-8"))
    return {}


def _print_status(incidents: dict[str, bool]) -> None:
    descriptions = _load_descriptions()
    print("\n  Incident Toggles")
    print("  " + "-" * 50)
    for name, active in incidents.items():
        state = "ON " if active else "OFF"
        desc = descriptions.get(name, "")
        print(f"  {name:<12} [{state}]  {desc}")
    print()


def _print_scenarios() -> None:
    descriptions = _load_descriptions()
    print("\n  Available Scenarios")
    print("  " + "-" * 50)
    for name in SCENARIOS:
        desc = descriptions.get(name, "")
        print(f"  {name:<12} {desc}")
    print()


def _request(path: str) -> dict:
    try:
        r = httpx.post(f"{BASE_URL}{path}", timeout=10.0)
        if r.status_code >= 400:
            detail = r.json().get("detail", r.text)
            print(f"Error ({r.status_code}): {detail}", file=sys.stderr)
            sys.exit(1)
        return r.json()
    except httpx.ConnectError:
        print(f"Error: Cannot connect to {BASE_URL}. Is the server running?", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print(f"Error: Request to {BASE_URL} timed out.", file=sys.stderr)
        sys.exit(1)


def _toggle(scenario: str, disable: bool) -> None:
    action = "disable" if disable else "enable"
    path = f"/incidents/{scenario}/{action}"
    result = _request(path)
    incidents = result.get("incidents", {})
    label = "Disabled" if disable else "Enabled"
    print(f"  {label} scenario: {scenario}")
    _print_status(incidents)


def _fire_chat(client: httpx.Client, payload: dict) -> dict:
    start = time.perf_counter()
    try:
        r = client.post(f"{BASE_URL}/chat", json=payload)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": r.status_code, "body": r.json(), "elapsed_ms": elapsed_ms}
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {"status": 0, "body": {"detail": str(exc)}, "elapsed_ms": elapsed_ms}


def _get_metrics(client: httpx.Client) -> dict:
    return client.get(f"{BASE_URL}/metrics", timeout=10.0).json()


# ---------------------------------------------------------------------------
# Attack 1: RAG Slow
# Enables rag_slow toggle, fires RAG-keyword requests, measures latency
# spike caused by the 2.5s sleep in retrieve().
# ---------------------------------------------------------------------------
def attack_rag_slow(n: int = 5, cleanup: bool = True) -> None:
    print("\n" + "=" * 60)
    print("  ATTACK: rag_slow  —  RAG Latency Spike")
    print("=" * 60)

    with httpx.Client(timeout=30.0) as client:
        # Baseline
        print("\n  [1/3] Collecting baseline latency (rag_slow OFF)...")
        base_latencies = []
        for payload in RAG_QUERIES[:n]:
            res = _fire_chat(client, payload)
            ms = res["elapsed_ms"]
            base_latencies.append(ms)
            print(f"    {res['status']}  {ms:.0f}ms  {payload['message'][:40]}")
        base_p50 = statistics.median(base_latencies)
        base_p95 = sorted(base_latencies)[max(0, int(len(base_latencies) * 0.95) - 1)]

        # Enable and attack
        print("\n  [2/3] Enabling rag_slow toggle and firing attack requests...")
        _request("/incidents/rag_slow/enable")
        atk_latencies = []
        for payload in RAG_QUERIES[:n]:
            res = _fire_chat(client, payload)
            ms = res["elapsed_ms"]
            atk_latencies.append(ms)
            print(f"    {res['status']}  {ms:.0f}ms  {payload['message'][:40]}")
        atk_p50 = statistics.median(atk_latencies)
        atk_p95 = sorted(atk_latencies)[max(0, int(len(atk_latencies) * 0.95) - 1)]

        # Cleanup
        if cleanup:
            print("\n  [3/3] Disabling rag_slow toggle...")
            _request("/incidents/rag_slow/disable")

    # Report
    print("\n  " + "-" * 50)
    print("  Impact Report")
    print("  " + "-" * 50)
    print(f"  Baseline  p50={base_p50:.0f}ms  p95={base_p95:.0f}ms")
    print(f"  Attack    p50={atk_p50:.0f}ms  p95={atk_p95:.0f}ms")
    print(f"  Delta     p50 +{atk_p50 - base_p50:.0f}ms  p95 +{atk_p95 - base_p95:.0f}ms")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Attack 2: Tool Fail
# Enables tool_fail toggle, fires RAG-keyword requests, observes 500 errors
# caused by RuntimeError("Vector store timeout") in retrieve().
# ---------------------------------------------------------------------------
def attack_tool_fail(n: int = 5, cleanup: bool = True) -> None:
    print("\n" + "=" * 60)
    print("  ATTACK: tool_fail  —  Vector Store Timeout")
    print("=" * 60)

    with httpx.Client(timeout=30.0) as client:
        # Baseline
        print("\n  [1/3] Collecting baseline error rate (tool_fail OFF)...")
        base_ok = 0
        base_err = 0
        for payload in RAG_QUERIES[:n]:
            res = _fire_chat(client, payload)
            if res["status"] < 400:
                base_ok += 1
            else:
                base_err += 1
            print(f"    {res['status']}  {payload['message'][:40]}")
        base_rate = (base_err / max(1, base_ok + base_err)) * 100

        # Enable and attack
        print("\n  [2/3] Enabling tool_fail toggle and firing attack requests...")
        _request("/incidents/tool_fail/enable")
        atk_ok = 0
        atk_err = 0
        error_types = []
        for payload in RAG_QUERIES[:n]:
            res = _fire_chat(client, payload)
            if res["status"] < 400:
                atk_ok += 1
            else:
                atk_err += 1
                detail = res["body"].get("detail", "unknown")
                error_types.append(detail)
            print(f"    {res['status']}  {payload['message'][:40]}  err={res['body'].get('detail', '')}")
        atk_rate = (atk_err / max(1, atk_ok + atk_err)) * 100

        # Cleanup
        if cleanup:
            print("\n  [3/3] Disabling tool_fail toggle...")
            _request("/incidents/tool_fail/disable")

    # Report
    print("\n  " + "-" * 50)
    print("  Impact Report")
    print("  " + "-" * 50)
    print(f"  Baseline  success={base_ok}  errors={base_err}  error_rate={base_rate:.1f}%")
    print(f"  Attack    success={atk_ok}  errors={atk_err}  error_rate={atk_rate:.1f}%")
    if error_types:
        print(f"  Error types seen: {set(error_types)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Attack 3: Cost Spike
# Enables cost_spike toggle, fires requests, measures token/cost increase
# caused by output_tokens *= 4 in FakeLLM.
# ---------------------------------------------------------------------------
def attack_cost_spike(n: int = 5, cleanup: bool = True) -> None:
    print("\n" + "=" * 60)
    print("  ATTACK: cost_spike  —  Token Usage / Cost Spike")
    print("=" * 60)

    with httpx.Client(timeout=30.0) as client:
        # Baseline
        print("\n  [1/3] Collecting baseline cost (cost_spike OFF)...")
        base_tokens_out = []
        base_costs = []
        for payload in COST_QUERIES[:n]:
            res = _fire_chat(client, payload)
            body = res["body"]
            if res["status"] < 400:
                base_tokens_out.append(body.get("tokens_out", 0))
                base_costs.append(body.get("cost_usd", 0))
            print(f"    {res['status']}  tokens_out={body.get('tokens_out', '-')}  cost=${body.get('cost_usd', '-'):>8.6f}")
        base_avg_tokens = statistics.mean(base_tokens_out) if base_tokens_out else 0
        base_total_cost = sum(base_costs)

        # Enable and attack
        print("\n  [2/3] Enabling cost_spike toggle and firing attack requests...")
        _request("/incidents/cost_spike/enable")
        atk_tokens_out = []
        atk_costs = []
        for payload in COST_QUERIES[:n]:
            res = _fire_chat(client, payload)
            body = res["body"]
            if res["status"] < 400:
                atk_tokens_out.append(body.get("tokens_out", 0))
                atk_costs.append(body.get("cost_usd", 0))
            print(f"    {res['status']}  tokens_out={body.get('tokens_out', '-')}  cost=${body.get('cost_usd', '-'):>8.6f}")
        atk_avg_tokens = statistics.mean(atk_tokens_out) if atk_tokens_out else 0
        atk_total_cost = sum(atk_costs)

        # Cleanup
        if cleanup:
            print("\n  [3/3] Disabling cost_spike toggle...")
            _request("/incidents/cost_spike/disable")

    # Report
    print("\n  " + "-" * 50)
    print("  Impact Report")
    print("  " + "-" * 50)
    print(f"  Baseline  avg_tokens_out={base_avg_tokens:.0f}  total_cost=${base_total_cost:.6f}")
    print(f"  Attack    avg_tokens_out={atk_avg_tokens:.0f}  total_cost=${atk_total_cost:.6f}")
    if base_total_cost > 0:
        print(f"  Cost multiplier: {atk_total_cost / base_total_cost:.1f}x")
    print("=" * 60)


ATTACK_MAP = {
    "rag_slow": attack_rag_slow,
    "tool_fail": attack_tool_fail,
    "cost_spike": attack_cost_spike,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject or clear incident scenarios on the running app")
    parser.add_argument("--scenario", choices=SCENARIOS, help="Scenario to enable/disable/attack")
    parser.add_argument("--disable", action="store_true", help="Disable the scenario instead of enabling it")
    parser.add_argument("--attack", action="store_true", help="Run a full attack: baseline + enable + fire requests + report + cleanup")
    parser.add_argument("--no-cleanup", action="store_true", help="Leave the toggle ON after attack (default: auto-disable)")
    parser.add_argument("-n", "--count", type=int, default=5, help="Number of requests per attack phase (default: 5)")
    parser.add_argument("--all", action="store_true", help="Enable/disable all scenarios at once")
    parser.add_argument("--status", action="store_true", help="Show current incident toggle states")
    parser.add_argument("--list", action="store_true", help="List available scenarios with descriptions")
    args = parser.parse_args()

    if args.list:
        _print_scenarios()
        return

    if args.status:
        try:
            r = httpx.get(f"{BASE_URL}/health", timeout=10.0)
            incidents = r.json().get("incidents", {})
        except httpx.ConnectError:
            print(f"Error: Cannot connect to {BASE_URL}. Is the server running?", file=sys.stderr)
            sys.exit(1)
        _print_status(incidents)
        return

    if args.attack:
        if not args.scenario and not args.all:
            parser.error("--attack requires --scenario <name> or --all")
        cleanup = not args.no_cleanup
        targets = SCENARIOS if args.all else [args.scenario]
        for name in targets:
            ATTACK_MAP[name](n=args.count, cleanup=cleanup)
        return

    if not args.scenario and not args.all:
        parser.error("Specify --scenario <name>, --all, --status, or --list")

    if args.all:
        for scenario in SCENARIOS:
            _toggle(scenario, args.disable)
    else:
        _toggle(args.scenario, args.disable)


if __name__ == "__main__":
    main()