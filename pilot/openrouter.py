"""Project-owned registration for the pinned BenchFlow provider registry."""

import base64
import json

from .config import ROOT, canonical_json

MODEL_ID = "openai/gpt-5.4-mini"
BENCHFLOW_MODEL = f"openrouter/{MODEL_ID}"
BASE_URL = "https://openrouter.ai/api/v1"


def model_metadata():
    model = json.loads((ROOT / "runtime/openrouter-model.json").read_text())["model"]
    if model["id"] != MODEL_ID:
        raise ValueError("Unexpected OpenRouter model metadata")
    if not {"tools", "reasoning"}.issubset(model["supported_parameters"]):
        raise ValueError("Selected model must advertise tools and reasoning")
    return {
        "id": MODEL_ID, "name": model["name"], "reasoning": True,
        "input": [kind for kind in model["architecture"]["input_modalities"] if kind in {"text", "image"}],
        "contextWindow": model["context_length"],
        "maxTokens": model["top_provider"]["max_completion_tokens"],
        "cost": {"input": float(model["pricing"]["prompt"]) * 1e6,
                 "output": float(model["pricing"]["completion"]) * 1e6,
                 "cacheRead": float(model["pricing"].get("input_cache_read", 0)) * 1e6,
                 "cacheWrite": 0},
    }


def register_openrouter():
    from benchflow.agents.providers import PROVIDERS, ProviderConfig
    from benchflow.providers.litellm_config import MODEL_COST_PER_TOKEN

    meta = model_metadata()
    PROVIDERS["openrouter"] = ProviderConfig(
        name="openrouter", base_url=BASE_URL, api_protocol="openai-completions",
        auth_type="api_key", auth_env="OPENROUTER_API_KEY", models=[meta],
    )
    # This route uses the OpenAI-compatible transport with the complete OR slug.
    # Costs remain estimates; cached-token/provider invoice reconciliation is separate.
    MODEL_COST_PER_TOKEN[MODEL_ID] = (meta["cost"]["input"] / 1e6, meta["cost"]["output"] / 1e6)


def agent_metadata_env():
    return {"PE6203_MODEL_METADATA": base64.b64encode(canonical_json(model_metadata()).encode()).decode()}


def route_record(model):
    from benchflow.providers.litellm_config import resolve_litellm_route

    if model != BENCHFLOW_MODEL:
        raise ValueError(f"The reviewed OpenRouter integration requires {BENCHFLOW_MODEL}")
    route = resolve_litellm_route(model, {})
    return {"requested_model": model, "model_alias": route.model_alias,
            "upstream_model": route.upstream_model, "api_base": route.litellm_params["api_base"],
            "required_env": list(route.required_env), "identity_kind": "configured_proxy_route_not_provider_attestation"}
