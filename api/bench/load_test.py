"""Submit real balloon work concurrently, poll every accepted task, and report observed limits."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import platform
import time
from typing import Any

import httpx


def sample_puzzle() -> dict[str, Any]:
    return {
        "rule_version": "center-torque-v1", "rows": 5, "columns": 5,
        "usable_cells": [{"row": row, "column": column} for row in range(5) for column in range(5)
                         if row in (0, 4) or column in (0, 4)],
        "inventory": [{"lift": lift, "count": 3} for lift in (6, 3, 2, 1)],
    }


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    return round(ordered[lower] + (ordered[min(lower + 1, len(ordered) - 1)] - ordered[lower]) *
                 (position - lower), 2)


def latency_summary(values: list[float]) -> dict[str, float | int | None]:
    return {"count": len(values), "p50_ms": percentile(values, .5), "p95_ms": percentile(values, .95),
            "max_ms": round(max(values), 2) if values else None}


def error_code(response: httpx.Response) -> str | None:
    try:
        detail = response.json().get("error", {})
        return detail.get("code") if isinstance(detail, dict) else None
    except (ValueError, AttributeError):
        return None


async def one_request(index: int, client: httpx.AsyncClient, start: asyncio.Event,
                      args: argparse.Namespace, image: bytes | None) -> dict[str, Any]:
    await start.wait()
    started = time.monotonic()
    item: dict[str, Any] = {"index": index, "submit_status": None, "submit_ms": None,
                            "submit_error_code": None, "transport_error": None,
                            "final_status": None, "outcome": None, "end_to_end_ms": None,
                            "poll_error": None}
    try:
        if args.mode == "solve":
            response = await client.post("/api/v1/puzzles/balloon/solve", json=sample_puzzle())
        else:
            response = await client.post("/api/v1/puzzles/balloon/recognize", files={
                "image": (Path(args.image).name, image, mimetypes.guess_type(args.image)[0] or "application/octet-stream")
            })
    except httpx.RequestError as exc:
        item["transport_error"] = type(exc).__name__
        return item
    item["submit_ms"] = round((time.monotonic() - started) * 1000, 2)
    item["submit_status"] = response.status_code
    if response.status_code != 202:
        item["submit_error_code"] = error_code(response)
        return item
    try:
        task_id = response.json()["id"]
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("missing task id")
    except (ValueError, KeyError, TypeError):
        item["poll_error"] = "invalid_task_id"
        return item

    deadline = started + args.task_deadline
    while time.monotonic() < deadline:
        try:
            task_response = await client.get(f"/api/v1/tasks/{task_id}")
            if task_response.status_code != 200:
                item["poll_error"] = f"HTTP_{task_response.status_code}"
                return item
            task = task_response.json()
            status = task.get("status")
            if status in ("succeeded", "failed", "cancelled"):
                item["final_status"] = status
                result = task.get("result")
                if status == "succeeded" and isinstance(result, dict):
                    item["outcome"] = result.get("outcome")
                item["end_to_end_ms"] = round((time.monotonic() - started) * 1000, 2)
                return item
            if status not in ("queued", "running"):
                item["poll_error"] = "invalid_task_status"
                return item
        except httpx.RequestError as exc:
            item["poll_error"] = type(exc).__name__
            return item
        except (ValueError, AttributeError):
            item["poll_error"] = "invalid_task_response"
            return item
        await asyncio.sleep(args.poll_interval)
    item["final_status"] = "deadline"
    return item


async def sample_health(client: httpx.AsyncClient, start: asyncio.Event,
                        stop: asyncio.Event, interval: float) -> list[dict[str, Any]]:
    await start.wait()
    records: list[dict[str, Any]] = []
    while not stop.is_set():
        began = time.monotonic()
        try:
            response = await client.get("/api/v1/health")
            records.append({"status": response.status_code, "ms": round((time.monotonic() - began) * 1000, 2)})
        except httpx.RequestError as exc:
            records.append({"status": type(exc).__name__, "ms": None})
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except asyncio.TimeoutError:
            pass
    return records


async def sample_process_tree(pid: int, start: asyncio.Event, stop: asyncio.Event,
                              interval: float) -> dict[str, Any]:
    import psutil

    root = psutil.Process(pid)
    root_created = root.create_time()
    previous: dict[tuple[int, float], float] = {}
    previous_at: float | None = None
    observed_cpu_seconds = 0.0
    peak_rss = 0
    peak_cpu_percent = 0.0
    samples = 0
    errors: Counter[str] = Counter()
    await start.wait()
    while not stop.is_set():
        now = time.monotonic()
        current: dict[tuple[int, float], float] = {}
        rss = 0
        try:
            if not root.is_running() or root.create_time() != root_created:
                errors["root_exited"] += 1
                break
            processes = [root, *root.children(recursive=True)]
        except psutil.Error as exc:
            errors[type(exc).__name__] += 1
            processes = []
        for process in processes:
            try:
                with process.oneshot():
                    identity = (process.pid, process.create_time())
                    times = process.cpu_times()
                    current[identity] = times.user + times.system
                    rss += process.memory_info().rss
            except psutil.Error:
                continue
        delta = sum(max(0.0, cpu - previous[identity]) for identity, cpu in current.items()
                    if identity in previous)
        observed_cpu_seconds += delta
        if previous_at is not None and now > previous_at:
            peak_cpu_percent = max(peak_cpu_percent, 100 * delta / (now - previous_at))
        peak_rss = max(peak_rss, rss)
        samples += 1
        previous, previous_at = current, now
        try:
            await asyncio.wait_for(stop.wait(), interval)
        except asyncio.TimeoutError:
            pass
    return {"pid": pid, "samples": samples, "peak_summed_rss_bytes": peak_rss,
            "peak_observed_cpu_percent_one_core": round(peak_cpu_percent, 2),
            "observed_cpu_seconds": round(observed_cpu_seconds, 3), "sampling_errors": dict(errors),
            "method": "RSS sums each live process and can double-count shared pages; short peaks, CPU before a new child first appears, and CPU of children exiting between samples may be missed."}


async def run(args: argparse.Namespace, image: bytes | None) -> dict[str, Any]:
    start = asyncio.Event()
    stop = asyncio.Event()
    limits = httpx.Limits(max_connections=max(args.concurrency + 5, 20),
                          max_keepalive_connections=max(args.concurrency + 5, 20))
    timeout = httpx.Timeout(connect=10.0, read=45.0, write=45.0, pool=10.0)
    async with httpx.AsyncClient(base_url=args.api_url.rstrip("/"), limits=limits, timeout=timeout) as client:
        health_task = asyncio.create_task(sample_health(client, start, stop, args.health_interval))
        process_task = asyncio.create_task(sample_process_tree(args.pid, start, stop, args.sample_interval)) if args.pid else None
        semaphore = asyncio.Semaphore(args.concurrency)

        async def bounded(index: int) -> dict[str, Any]:
            async with semaphore:
                return await one_request(index, client, start, args, image)

        requests = [asyncio.create_task(bounded(index)) for index in range(args.requests)]
        began = time.monotonic()
        start.set()
        try:
            results = await asyncio.gather(*requests)
        finally:
            stop.set()
        health = await health_task
        process = await process_task if process_task else None
    submit_times = [item["submit_ms"] for item in results if item["submit_ms"] is not None]
    end_to_end = [item["end_to_end_ms"] for item in results if item["end_to_end_ms"] is not None]
    health_times = [item["ms"] for item in health if item["ms"] is not None]
    return {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"platform": platform.platform(), "python": platform.python_version(),
                        "logical_cpus": os.cpu_count()},
        "config": {"api_url": args.api_url, "mode": args.mode, "requests": args.requests,
                   "concurrency": args.concurrency, "task_deadline_seconds": args.task_deadline,
                   "image_name": Path(args.image).name if args.image else None,
                   "image_bytes": len(image) if image else None, "api_pid": args.pid},
        "elapsed_seconds": round(time.monotonic() - began, 2),
        "submissions": {"accepted_202": sum(item["submit_status"] == 202 for item in results),
                        "rejected_429": sum(item["submit_status"] == 429 for item in results),
                        "other_http_statuses": dict(Counter(str(item["submit_status"]) for item in results
                                                           if item["submit_status"] not in (None, 202, 429))),
                        "error_codes": dict(Counter(item["submit_error_code"] for item in results
                                                    if item["submit_error_code"])),
                        "transport_errors": dict(Counter(item["transport_error"] for item in results
                                                         if item["transport_error"])),
                        "latency": latency_summary(submit_times)},
        "tasks": {"final_statuses": dict(Counter(item["final_status"] or "unresolved" for item in results
                                                if item["submit_status"] == 202)),
                  "outcomes": dict(Counter(item["outcome"] for item in results if item["outcome"])),
                  "poll_errors": dict(Counter(item["poll_error"] for item in results if item["poll_error"])),
                  "end_to_end_latency": latency_summary(end_to_end)},
        "health": {"samples": len(health), "statuses": dict(Counter(str(item["status"]) for item in health)),
                   "latency": latency_summary(health_times)},
        "process_tree": process,
        "request_results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mode", choices=("solve", "recognize"), required=True)
    parser.add_argument("--image", help="Real screenshot path; required for recognize mode")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--task-deadline", type=float, default=210.0)
    parser.add_argument("--poll-interval", type=float, default=.25)
    parser.add_argument("--health-interval", type=float, default=.5)
    parser.add_argument("--sample-interval", type=float, default=.25)
    parser.add_argument("--pid", type=int, help="Optional API process PID to sample, not the load driver PID")
    parser.add_argument("--output", type=Path, help="Optional JSON report file")
    args = parser.parse_args()
    if args.requests < 1 or args.concurrency < 1 or args.task_deadline <= 0 or any(
        value <= 0 for value in (args.poll_interval, args.health_interval, args.sample_interval)
    ):
        parser.error("counts and intervals must be positive")
    if not args.api_url.startswith(("http://", "https://")):
        parser.error("--api-url must be an HTTP(S) URL")
    image = None
    if args.mode == "recognize":
        if not args.image or not Path(args.image).is_file():
            parser.error("recognize mode requires --image pointing to an existing real screenshot")
        image = Path(args.image).read_bytes()
        if not image or len(image) > 12 * 1024 * 1024:
            parser.error("screenshot must be nonempty and at most 12 MiB")
    if args.pid:
        import psutil
        if not psutil.pid_exists(args.pid):
            parser.error("--pid is not a live process")
    report = asyncio.run(run(args, image))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
