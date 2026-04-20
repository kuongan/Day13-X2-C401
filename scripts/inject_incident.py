from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8000"
SCENARIOS = ["rag_slow", "tool_fail", "cost_spike"]
INCIDENTS_FILE = Path("data/incidents.json")


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject or clear incident scenarios on the running app")
    parser.add_argument("--scenario", choices=SCENARIOS, help="Scenario to enable/disable")
    parser.add_argument("--disable", action="store_true", help="Disable the scenario instead of enabling it")
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

    if not args.scenario and not args.all:
        parser.error("Specify --scenario <name>, --all, --status, or --list")

    if args.all:
        for scenario in SCENARIOS:
            _toggle(scenario, args.disable)
    else:
        _toggle(args.scenario, args.disable)


if __name__ == "__main__":
    main()
