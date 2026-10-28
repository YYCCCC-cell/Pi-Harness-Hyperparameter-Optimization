#!/usr/bin/env python3
"""Transparent RPC transport audit. Does not inject prompts, commands or tools."""

import json
from pathlib import Path
import subprocess
import sys
import threading


def summary(event):
    if event.get("type") == "response" and event.get("command") == "get_state":
        state = event.get("data") or {}
        model = state.get("model") or {}
        return {"event": "get_state", "thinking_level": state.get("thinkingLevel"),
                "model": {key: model.get(key) for key in ("provider", "id", "api", "contextWindow")}}
    if event.get("type") == "message_end":
        message = event.get("message") or {}
        if message.get("role") == "assistant":
            return {"event": "assistant_message_end", "provider": message.get("provider"),
                    "model": message.get("model"), "stop_reason": message.get("stopReason")}
    if event.get("type") in {"auto_compaction_start", "auto_compaction_end", "auto_retry_start", "agent_settled"}:
        return {"event": event["type"]}
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
            for line in child.stdout:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
                try:
                    record = summary(json.loads(line))
                except (ValueError, AttributeError, TypeError):
                    record = None
                if record:
                    audit.write(json.dumps(record) + "\n")
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
