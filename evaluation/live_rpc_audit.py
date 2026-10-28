#!/usr/bin/env python3
"""Transparent Pi 1.4 RPC audit; no commands or context are injected.

Only scalar metering/control fields are retained, never prompt/tool/summary text.
The reviewed pilot wrapper is intentionally left unchanged.
"""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time


def summary(event):
    kind = event.get("type")
    if kind == "response" and event.get("command") == "get_state":
        state = event.get("data") or {}
        model = state.get("model") or {}
        return {"event": "get_state", "thinking_level": state.get("thinkingLevel"),
                "model": {k: model.get(k) for k in ("provider", "id", "api", "contextWindow", "maxTokens")}}
    if kind == "message_end":
        message = event.get("message") or {}
        if message.get("role") == "assistant":
            usage = message.get("usage") or {}
            return {"event": "assistant_message_end", "provider": message.get("provider"),
                    "model": message.get("model"), "stop_reason": message.get("stopReason"),
                    "usage": {k: usage.get(k) for k in ("input", "output", "cacheRead", "cacheWrite", "totalTokens")}}
    if kind in {"compaction_start", "compaction_end"}:
        record = {"event": kind, "reason": event.get("reason")}
        if kind == "compaction_end":
            result = event.get("result") or {}
            record.update(aborted=event.get("aborted"), will_retry=event.get("willRetry"),
                          has_error=bool(event.get("errorMessage")), completed=bool(result),
                          result={k: result.get(k) for k in
                                  ("firstKeptEntryId", "tokensBefore", "estimatedTokensAfter")})
        return record
    if kind in {"agent_settled", "auto_retry_start", "auto_retry_end"}:
        return {"event": kind, **{k: event[k] for k in ("attempt", "maxAttempts", "success", "aborted") if k in event}}
    return None


def main():
    child = subprocess.Popen(["/opt/benchflow/bin/pi", *sys.argv[1:]],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None, bufsize=0)

    def forward_input():
        try:
            for line in sys.stdin.buffer:
                child.stdin.write(line)
        except (BrokenPipeError, OSError):
            pass
        finally:
            child.stdin.close()

    threading.Thread(target=forward_input, daemon=True).start()
    try:
        with Path("/logs/agent/pi-rpc-audit.jsonl").open("a", buffering=1) as audit:
            audit.write(json.dumps({"event": "audit_start", "schema_version": 2}) + "\n")
            for line in child.stdout:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
                try:
                    record = summary(json.loads(line))
                except (ValueError, AttributeError, TypeError):
                    record = {"event": "audit_parse_error"}
                if record:
                    audit.write(json.dumps(dict(record, monotonic_seconds=time.monotonic())) + "\n")
    finally:
        if child.poll() is None:
            child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())
