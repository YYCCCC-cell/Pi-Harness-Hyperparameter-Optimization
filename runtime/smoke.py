"""Runs inside --network none. Only a loopback fixture answers model requests."""

import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import tempfile
import threading
import time


ALIAS = "benchflow-openrouter-openai-gpt-5.4-mini"
requests = []
spec = importlib.util.spec_from_file_location("launch", "/opt/pe6203/launch.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(payload)
        has_tool_result = any(m.get("role") == "tool" for m in payload["messages"])
        if has_tool_result:
            delta = {"role": "assistant", "content": "Offline fixture complete."}
            finish = "stop"
        else:
            delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": "offline_write",
                "type": "function", "function": {"name": "write", "arguments": json.dumps(
                    {"path": "offline-proof.txt", "content": "PI_TOOL_EXECUTED\n"})}}]}
            finish = "tool_calls"
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for data, end in [(delta, None), ({}, finish)]:
            chunk = {"id": "offline-fixture", "object": "chat.completion.chunk", "created": 1,
                     "model": ALIAS, "choices": [{"index": 0, "delta": data, "finish_reason": end}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def start_process(command, env, cwd):
    process = subprocess.Popen(command, env=env, cwd=cwd, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               bufsize=1, start_new_session=True)
    messages, errors = queue.Queue(), []

    def read_lines(stream, destination):
        for line in stream:
            if destination is messages:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    errors.append(line)
            else:
                errors.append(line)
    threading.Thread(target=read_lines, args=(process.stdout, messages), daemon=True).start()
    threading.Thread(target=read_lines, args=(process.stderr, errors), daemon=True).start()
    return process, messages, errors


def receive(messages, predicate, errors, timeout=45):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            message = messages.get(timeout=min(1, end-time.monotonic()))
        except queue.Empty:
            continue
        if predicate(message):
            return message
    raise RuntimeError("Protocol timeout: " + "".join(errors)[-2500:])


def send(process, value):
    process.stdin.write(json.dumps(value) + "\n")
    process.stdin.flush()


def stop(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    for stream in (process.stdin, process.stdout, process.stderr):
        stream.close()


def exercise(level, protocol, base_url, metadata):
    with tempfile.TemporaryDirectory(prefix="pi-offline-") as work:
        root = Path(work)
        env = dict(os.environ, HOME=work, PI_OFFLINE="1",
                   BENCHFLOW_PROVIDER_NAME="litellm", BENCHFLOW_PROVIDER_MODEL=ALIAS,
                   BENCHFLOW_PROVIDER_BASE_URL=base_url, BENCHFLOW_PROVIDER_API_KEY="offline-fixture-key",
                   PE6203_PI_SETTINGS=base64.b64encode(json.dumps({"defaultThinkingLevel": level,
                       "compaction": {"reserveTokens": 16384, "keepRecentTokens": 20000}}).encode()).decode(),
                   PE6203_MODEL_METADATA=base64.b64encode(json.dumps(metadata).encode()).decode())
        before = len(requests)
        if protocol == "rpc":
            launcher.configure(root / ".pi/agent", root / "logs", env)
            command = ["/opt/benchflow/bin/pi", "--mode", "rpc", "--no-themes"]
        else:
            command = ["python3", "/opt/pe6203/launch.py"]
        process, messages, errors = start_process(command, env, root)
        try:
            if protocol == "rpc":
                send(process, {"id": "state", "type": "get_state"})
                state = receive(messages, lambda m: m.get("id") == "state", errors)
                assert state["success"] and state["data"]["thinkingLevel"] == level, (state, errors)
                assert state["data"]["model"]["id"] == ALIAS, state
                send(process, {"id": "prompt", "type": "prompt", "message": "Write the offline proof file."})
                receive(messages, lambda m: m.get("type") == "agent_end", errors)
            else:
                send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                               "params": {"protocolVersion": 1, "clientCapabilities": {}}})
                init = receive(messages, lambda m: m.get("id") == 1, errors)
                assert "result" in init, init
                send(process, {"jsonrpc": "2.0", "id": 2, "method": "session/new",
                               "params": {"cwd": work, "mcpServers": []}})
                session = receive(messages, lambda m: m.get("id") == 2, errors)
                assert "result" in session, session
                session_id = session["result"]["sessionId"]
                assert any(o["id"] == "model" for o in session["result"]["configOptions"]), session
                send(process, {"jsonrpc": "2.0", "id": 3, "method": "session/set_config_option",
                               "params": {"sessionId": session_id, "configId": "model", "value": ALIAS}})
                selected = receive(messages, lambda m: m.get("id") == 3, errors)
                assert "result" in selected, selected
                send(process, {"jsonrpc": "2.0", "id": 4, "method": "session/prompt",
                               "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Write the offline proof file."}]}})
                answer = receive(messages, lambda m: m.get("id") == 4, errors)
                assert "result" in answer, answer
            assert (root / "offline-proof.txt").read_text() == "PI_TOOL_EXECUTED\n"
            actual = requests[before:]
            assert len(actual) >= 2, actual
            assert all(r.get("reasoning_effort") == level for r in actual), actual
            assert all(r["model"] == ALIAS for r in actual), actual
            return {"protocol": protocol, "thinking_level": level, "tool_write_verified": True,
                    "fixture_requests": len(actual), "reasoning_effort_verified": True}
        finally:
            stop(process)


def main():
    metadata = json.loads(Path("/smoke/model.json").read_text())
    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/v1"
        checks = [exercise(level, "rpc", url, metadata) for level in ("low", "medium", "high")]
        checks.append(exercise("medium", "acp", url, metadata))
        print(json.dumps({"status": "passed", "kind": "offline_fixture_not_benchmark",
                          "real_model_calls": 0, "checks": checks}, indent=2))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
