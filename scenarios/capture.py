"""Shared trace capture.

Import this module from any scenario file and it will record every request the
scenario makes as one JSON line in the trace file (default: trace.jsonl).
Each line is one request/response: {step, method, endpoint, status, response}.

The detector reads that trace later. Capture knows nothing about the detector,
and nothing about which API is being tested.
"""
import json
import os

from locust import events

TRACE_PATH = os.environ.get("TRACE_PATH", "trace.jsonl")
_trace = None


@events.test_start.add_listener
def _open(environment, **kw):
    global _trace
    _trace = open(TRACE_PATH, "w")
    print(f"\n[capture] writing trace to {TRACE_PATH}\n")


@events.test_stop.add_listener
def _close(environment, **kw):
    global _trace
    if _trace:
        _trace.close()
        _trace = None
        print(f"\n[capture] trace complete: {TRACE_PATH}\n")


@events.request.add_listener
def _record(request_type, name, response, context, **kw):
    if _trace is None:
        return

    status, body = None, None
    if response is not None:
        status = getattr(response, "status_code", None)
        try:
            body = response.json()
        except Exception:
            body = None

    step = (context or {}).get("step")
    _trace.write(json.dumps({
        "step": step,
        "method": request_type,
        "endpoint": name,
        "status": status,
        "response": body,
    }) + "\n")
    _trace.flush()
    print(f"  [{step or '?'}] {request_type:5} {name:30} -> {status}")
