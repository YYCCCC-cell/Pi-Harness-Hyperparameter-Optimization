"""Container integration test: real Pi + bundled skills, local fixture only."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import pwd
import tempfile
import threading

spec = importlib.util.spec_from_file_location("fixture", "/opt/pe6203/offline_fixture.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def main():
    metadata = json.loads(Path("/opt/pe6203/smoke-model.json").read_text())
    server = fixture.ThreadingHTTPServer(("127.0.0.1", 18762), fixture.Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    identity = pwd.getpwnam("agent")
    try:
        for level, reserve, recent, protocol in (("low", 8192, 10000, "rpc"),
                ("medium", 16384, 20000, "rpc"), ("high", 32768, 40000, "rpc"),
                ("medium", 16384, 20000, "acp")):
            with tempfile.TemporaryDirectory() as directory:
                os.chown(directory, identity.pw_uid, identity.pw_gid)
                settings = {"defaultThinkingLevel": level, "compaction": {"reserveTokens": reserve, "keepRecentTokens": recent}}
                env = dict(os.environ, HOME="/home/agent", PI_OFFLINE="1",
                           PI_CODING_AGENT_DIR="/home/agent/.pi/agent",
                           BENCHFLOW_PROVIDER_NAME="litellm", BENCHFLOW_PROVIDER_MODEL=fixture.ALIAS,
                           BENCHFLOW_PROVIDER_BASE_URL="http://127.0.0.1:18762/v1",
                           BENCHFLOW_PROVIDER_API_KEY="offline-fixture-no-paid-credential",
                           PE6203_PI_SETTINGS=base64.b64encode(json.dumps(settings).encode()).decode(),
                           PE6203_MODEL_METADATA=base64.b64encode(json.dumps(metadata).encode()).decode())
                fixture.launcher.configure(Path(env["PI_CODING_AGENT_DIR"]), Path("/logs/agent/offline-smoke"), dict(env))
                for p in Path(env["PI_CODING_AGENT_DIR"]).glob("*.json"):
                    os.chown(p, identity.pw_uid, identity.pw_gid)
                before = len(fixture.requests)
                command = (["/opt/benchflow/bin/pi", "--mode", "rpc", "--no-themes"] if protocol == "rpc" else
                           ["python3", "/opt/pe6203/launch.py"])
                process, messages, errors = fixture.start_process(["runuser", "-u", "agent", "--", *command], env, directory)
                try:
                    skills = []
                    if protocol == "rpc":
                        fixture.send(process, {"id": "state", "type": "get_state"})
                        state = fixture.receive(messages, lambda m: m.get("id") == "state", errors)
                        assert state["success"] and state["data"]["thinkingLevel"] == level, state
                        fixture.send(process, {"id": "skills", "type": "get_commands"})
                        commands = fixture.receive(messages, lambda m: m.get("id") == "skills", errors)
                        skills = [c["name"] for c in commands["data"]["commands"] if c.get("source") == "skill"]
                        assert skills, commands
                        fixture.send(process, {"id": "prompt", "type": "prompt", "message": "Write the offline proof file."})
                        fixture.receive(messages, lambda m: m.get("type") == "agent_end", errors)
                    else:
                        fixture.send(process, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                               "params": {"protocolVersion": 1, "clientCapabilities": {}}})
                        init = fixture.receive(messages, lambda m: m.get("id") == 1, errors)
                        assert "result" in init, init
                        fixture.send(process, {"jsonrpc": "2.0", "id": 2, "method": "session/new",
                                               "params": {"cwd": directory, "mcpServers": []}})
                        session = fixture.receive(messages, lambda m: m.get("id") == 2, errors)
                        session_id = session["result"]["sessionId"]
                        fixture.send(process, {"jsonrpc": "2.0", "id": 3, "method": "session/set_config_option",
                                               "params": {"sessionId": session_id, "configId": "model", "value": fixture.ALIAS}})
                        selected = fixture.receive(messages, lambda m: m.get("id") == 3, errors)
                        assert "result" in selected, selected
                        fixture.send(process, {"jsonrpc": "2.0", "id": 4, "method": "session/prompt",
                                               "params": {"sessionId": session_id, "prompt": [{"type": "text", "text": "Write the offline proof file."}]}})
                        answer = fixture.receive(messages, lambda m: m.get("id") == 4, errors)
                        assert "result" in answer, answer
                    assert (Path(directory) / "offline-proof.txt").read_text() == "PI_TOOL_EXECUTED\n"
                    calls = fixture.requests[before:]
                    assert len(calls) >= 2 and all(c.get("reasoning_effort") == level for c in calls)
                    written = json.loads(Path(env["PI_CODING_AGENT_DIR"], "settings.json").read_text())
                    assert written["compaction"] == settings["compaction"]
                    checks.append({"settings": settings, "protocol": protocol, "skills_discovered": skills,
                                   "fixture_requests": len(calls), "real_pi_tool_write": True})
                finally:
                    fixture.stop(process)
        print(json.dumps({"kind": "offline_fixture_not_model_evaluation", "paid_api_calls": 0, "checks": checks}))
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
