#!/usr/bin/env python3
"""Configure native Pi through models.json/settings.json, then exec pi-acp."""

import base64
import json
import os
from pathlib import Path


def configure(directory, log_directory, env):
    directory.mkdir(parents=True, exist_ok=True)
    settings = json.loads(base64.b64decode(env.pop("PE6203_PI_SETTINGS")))
    meta = json.loads(base64.b64decode(env.pop("PE6203_MODEL_METADATA")))
    provider, model = env["BENCHFLOW_PROVIDER_NAME"], env["BENCHFLOW_PROVIDER_MODEL"]
    if provider != "litellm" or not env.get("BENCHFLOW_PROVIDER_API_KEY"):
        raise ValueError("Pi must use the metered BenchFlow proxy")
    settings.update(defaultProvider=provider, defaultModel=model)
    meta["id"] = model
    # The local proxy speaks the OpenAI-compatible protocol. OpenRouter accepts
    # reasoning_effort; preserve the three levels when the proxy hides its URL.
    meta["compat"] = {"thinkingFormat": "openai", "supportsReasoningEffort": True,
                      "maxTokensField": "max_completion_tokens"}
    models = {"providers": {provider: {"api": "openai-completions",
              "baseUrl": env["BENCHFLOW_PROVIDER_BASE_URL"],
              "apiKey": "$BENCHFLOW_PROVIDER_API_KEY", "models": [meta]}}}
    (directory / "models.json").write_text(json.dumps(models, indent=2) + "\n")
    (directory / "settings.json").write_text(json.dumps(settings, sort_keys=True, indent=2) + "\n")
    log_directory.mkdir(parents=True, exist_ok=True)
    (log_directory / "pi-settings-written.json").write_text(json.dumps(settings, indent=2) + "\n")
    return settings


def main():
    directory = Path.home() / ".pi/agent"
    configure(directory, Path("/logs/agent"), os.environ)
    os.environ["PI_CODING_AGENT_DIR"] = str(directory)
    os.environ["PI_ACP_PI_COMMAND"] = "/opt/pe6203/pi_rpc_audit.py"
    os.environ["PI_OFFLINE"] = "1"
    os.environ["PATH"] = "/opt/benchflow/bin:" + os.environ.get("PATH", "")
    os.execv("/opt/benchflow/bin/pi-acp", ["pi-acp"])


if __name__ == "__main__":
    main()
