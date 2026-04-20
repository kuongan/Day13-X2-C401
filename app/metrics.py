from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from statistics import mean

REQUEST_LATENCIES: list[int] = []
REQUEST_COSTS: list[float] = []
REQUEST_TOKENS_IN: list[int] = []
REQUEST_TOKENS_OUT: list[int] = []
ERRORS: Counter[str] = Counter()
TRAFFIC: int = 0
QUALITY_SCORES: list[float] = []
REQUEST_EVENTS: list[dict] = []
ERROR_EVENTS: list[dict] = []


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat().replace("+00:00", "Z")


def record_request(latency_ms: int, cost_usd: float, tokens_in: int, tokens_out: int, quality_score: float) -> None:
    global TRAFFIC
    TRAFFIC += 1
    REQUEST_LATENCIES.append(latency_ms)
    REQUEST_COSTS.append(cost_usd)
    REQUEST_TOKENS_IN.append(tokens_in)
    REQUEST_TOKENS_OUT.append(tokens_out)
    QUALITY_SCORES.append(quality_score)
    REQUEST_EVENTS.append(
        {
            "ts": _now_utc(),
            "latency_ms": latency_ms,
            "cost_usd": float(cost_usd),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "quality_score": float(quality_score),
        }
    )



def record_error(error_type: str) -> None:
    ERRORS[error_type] += 1
    ERROR_EVENTS.append({"ts": _now_utc(), "error_type": error_type})



def percentile(values: list[int], p: int) -> float:
    if not values:
        return 0.0
    items = sorted(values)
    idx = max(0, min(len(items) - 1, round((p / 100) * len(items) + 0.5) - 1))
    return float(items[idx])



def snapshot() -> dict:
    total_errors = sum(ERRORS.values())
    error_rate_pct = round((total_errors / TRAFFIC) * 100, 3) if TRAFFIC else 0.0
    quality_avg = round(mean(QUALITY_SCORES), 4) if QUALITY_SCORES else 0.0
    quality_proxy_hallucination_pct = round(
        (sum(1 for q in QUALITY_SCORES if q < 0.7) / len(QUALITY_SCORES)) * 100,
        3,
    ) if QUALITY_SCORES else 0.0
    return {
        "traffic": TRAFFIC,
        "latency_p50": percentile(REQUEST_LATENCIES, 50),
        "latency_p95": percentile(REQUEST_LATENCIES, 95),
        "latency_p99": percentile(REQUEST_LATENCIES, 99),
        "avg_cost_usd": round(mean(REQUEST_COSTS), 4) if REQUEST_COSTS else 0.0,
        "total_cost_usd": round(sum(REQUEST_COSTS), 4),
        "tokens_in_total": sum(REQUEST_TOKENS_IN),
        "tokens_out_total": sum(REQUEST_TOKENS_OUT),
        "error_breakdown": dict(ERRORS),
        "error_rate_pct": error_rate_pct,
        "quality_avg": quality_avg,
        "quality_proxy_hallucination_pct": quality_proxy_hallucination_pct,
    }


def dashboard_snapshot(window_minutes: int = 60, bucket_seconds: int = 60) -> dict:
    now = _now_utc()
    bucket_seconds = max(10, int(bucket_seconds))
    window_minutes = max(1, int(window_minutes))
    window_start = now - timedelta(minutes=window_minutes)

    series: dict[datetime, dict] = {}

    def _bucket(ts: datetime) -> datetime:
        floored = ts - timedelta(seconds=ts.second % bucket_seconds, microseconds=ts.microsecond)
        return floored

    def _ensure(ts: datetime) -> dict:
        if ts not in series:
            series[ts] = {
                "latencies": [],
                "requests": 0,
                "cost_usd": 0.0,
                "tokens_in": 0,
                "tokens_out": 0,
                "quality_scores": [],
                "errors": 0,
                "errors_4xx": 0,
                "errors_5xx": 0,
            }
        return series[ts]

    for event in REQUEST_EVENTS:
        ts = event["ts"]
        if ts < window_start:
            continue
        bucket = _bucket(ts)
        point = _ensure(bucket)
        point["latencies"].append(int(event["latency_ms"]))
        point["requests"] += 1
        point["cost_usd"] += float(event["cost_usd"])
        point["tokens_in"] += int(event["tokens_in"])
        point["tokens_out"] += int(event["tokens_out"])
        point["quality_scores"].append(float(event["quality_score"]))

    for event in ERROR_EVENTS:
        ts = event["ts"]
        if ts < window_start:
            continue
        bucket = _bucket(ts)
        point = _ensure(bucket)
        point["errors"] += 1
        # This lab returns server-side exceptions as 5xx from /chat.
        point["errors_5xx"] += 1

    buckets_sorted = sorted(series.keys())

    latency_points = []
    traffic_points = []
    error_points = []
    cost_points = []
    tokens_points = []
    quality_points = []

    for bucket in buckets_sorted:
        point = series[bucket]
        requests = int(point["requests"])
        errors = int(point["errors"])
        total = requests + errors
        q_scores = point["quality_scores"]
        hallucination_pct = round((sum(1 for q in q_scores if q < 0.7) / len(q_scores)) * 100, 3) if q_scores else 0.0
        ts_iso = _iso(bucket)

        latency_points.append(
            {
                "ts": ts_iso,
                "p50_ms": percentile(point["latencies"], 50),
                "p95_ms": percentile(point["latencies"], 95),
                "p99_ms": percentile(point["latencies"], 99),
            }
        )
        traffic_points.append(
            {
                "ts": ts_iso,
                "requests": requests,
                "qps": round(requests / bucket_seconds, 4),
            }
        )
        error_points.append(
            {
                "ts": ts_iso,
                "error_rate_pct": round((errors / total) * 100, 3) if total else 0.0,
                "errors_total": errors,
                "errors_4xx": int(point["errors_4xx"]),
                "errors_5xx": int(point["errors_5xx"]),
                "total_requests": total,
            }
        )
        hourly_cost = float(point["cost_usd"]) * (3600 / bucket_seconds)
        cost_points.append(
            {
                "ts": ts_iso,
                "cost_usd": round(float(point["cost_usd"]), 6),
                "cost_usd_per_hour": round(hourly_cost, 6),
            }
        )
        tokens_points.append(
            {
                "ts": ts_iso,
                "tokens_in": int(point["tokens_in"]),
                "tokens_out": int(point["tokens_out"]),
            }
        )
        quality_points.append(
            {
                "ts": ts_iso,
                "quality_avg": round(mean(q_scores), 4) if q_scores else 0.0,
                "hallucination_pct": hallucination_pct,
            }
        )

    return {
        "generated_at": _iso(now),
        "window_minutes": window_minutes,
        "bucket_seconds": bucket_seconds,
        "slo_lines": {
            "latency_p95_ms": 2000,
            "error_rate_pct": 1.0,
            "cost_usd_per_hour": 5.0,
            "hallucination_pct": 5.0,
        },
        "summary": snapshot(),
        "panels": {
            "latency": latency_points,
            "traffic": traffic_points,
            "error_rate": error_points,
            "cost": cost_points,
            "tokens": tokens_points,
            "quality": quality_points,
        },
    }
