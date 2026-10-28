"""Process boundary between HPO and real, task-native SkillsBench rollouts.

This module imports no BenchFlow code. The independently pinned runtime Python
owns prompts, task environments, skills and verifiers; optimizers get metrics.
"""

import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

from pilot.config import ROOT, canonical_json
from hpo.config import read_json
from hpo.evaluation import unavailable_result

VERSION = "skillsbench_pi_v1"


def audit_usage_records(records):
    """Reject partially metered traces; BenchFlow's aggregate accepts ANY usage."""
    total_cost, inputs, outputs = 0.0, 0, 0
    complete = bool(records)
    for row in records:
        usage = row.get("usage") or {}
        incoming = usage.get("prompt_tokens", usage.get("input_tokens"))
        outgoing = usage.get("completion_tokens", usage.get("output_tokens"))
        cost = row.get("response_cost")
        valid = (row.get("event") == "success" and type(incoming) is int and incoming >= 0
                 and type(outgoing) is int and outgoing >= 0 and type(cost) in (int, float)
                 and math.isfinite(cost) and cost >= 0)
        complete = complete and valid
        if valid:
            total_cost += cost
            inputs += incoming
            outputs += outgoing
    return {"complete": complete, "model_api_calls": len(records),
            "estimated_cost_usd": total_cost if complete else None,
            "input_tokens": inputs if complete else None, "output_tokens": outputs if complete else None}


def isolated_env(home, key_name=None):
    home.mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in (
        "PATH", "SYSTEMROOT", "TMPDIR", "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_CONFIG"
    ) if k in os.environ}
    env.setdefault("DOCKER_CONFIG", str(Path.home() / ".docker"))
    env.update(HOME=str(home), PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
               BENCHFLOW_DOTENV_PATH=os.devnull)
    if key_name and os.environ.get(key_name):
        env[key_name] = os.environ[key_name]
    return env


def stop_process(child):
    errors = []
    # Include proxy/compose child processes, even when the worker already exited.
    for sig, timeout in ((signal.SIGTERM, 10), (signal.SIGKILL, 5)):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            break
        except OSError as exc:
            errors.append(type(exc).__name__)
            # A signal error must never bypass the exact-label Docker reaper.
            break
        try:
            child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        # A descendant can outlive the group leader; always kill the group too.
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            errors.append(type(exc).__name__)
        break
    return errors


def cleanup_project(project, env):
    """Remove and verify ONLY resources with this attempt's exact Compose label."""
    if not project.startswith("pe6203-") or len(project) != 39:
        raise ValueError("Invalid attempt project identity")
    label = f"label=com.docker.compose.project={project}"
    report = {"project": project, "removed": {}, "remaining": {}, "errors": []}
    for kind, listing, removal in (
        ("containers", ["ps", "-aq"], ["rm", "-f", "-v"]),
        ("networks", ["network", "ls", "-q"], ["network", "rm"]),
        ("volumes", ["volume", "ls", "-q"], ["volume", "rm"]),
    ):
        try:
            def query():
                return subprocess.run(["docker", *listing, "--filter", label], env=env,
                                      capture_output=True, text=True, timeout=30, check=True).stdout.split()
            ids = query()
            if ids:
                subprocess.run(["docker", *removal, *ids], env=env, capture_output=True,
                               text=True, timeout=45, check=True)
            report["removed"][kind] = ids
            report["remaining"][kind] = query()
        except (OSError, subprocess.SubprocessError) as exc:
            report["errors"].append(f"{kind}:{type(exc).__name__}")
    report["verified"] = not report["errors"] and not any(report["remaining"].values())
    return report


def runtime_python(config):
    # Resolving the python symlink would escape the venv and lose its dependencies.
    return str((ROOT / config["runtime_python"]).absolute())


def prepare_live(config, tasks, output, *, require_credentials=False, evaluation_access=None):
    """Read-only planning/preflight; no builds, model calls or solver execution."""
    from evaluation.panels import authorize_tasks
    authorize_tasks(config, list(tasks), evaluation_access)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False, mode=0o700)
    request = {"live": config, "tasks": list(tasks), "require_credentials": require_credentials}
    if evaluation_access is not None:
        request["evaluation_access"] = evaluation_access
    (output / "request.json").write_text(canonical_json(request))
    env = isolated_env(output / "home", config["api_key_env"] if require_credentials else None)
    result = subprocess.run([runtime_python(config), "-m", "evaluation.live_worker", "prepare", str(output)],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    secret = env.get(config["api_key_env"])
    (output / "worker.stderr.log").write_text(result.stderr.replace(secret, "[REDACTED]") if secret else result.stderr)
    if result.returncode:
        # Do not reflect arbitrary subprocess stderr (potential credentials) into journals.
        raise RuntimeError("Live preflight worker failed; check runtime_python and its BenchFlow dependencies")
    return read_json(output / "preflight.json")


def normalize_result(raw, task, model, elapsed, *, dispatched, interrupted=False):
    result = unavailable_result(task, "missing_result")
    result.update(model=model, harness_version=VERSION, wall_time_seconds=elapsed,
                  model_api_calls=None, measurement_error=None)
    if raw is None:
        if not dispatched:
            result.update(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
                          usage_kind="not_dispatched", actual_cost_usd=0,
                          cost_source="verified_before_provider_setup", model_api_calls=0)
        if interrupted:
            result["failure_reason"] = "timeout"
        return result
    if raw.get("task_name") != task or raw.get("model") != model:
        raise ValueError("BenchFlow result identity mismatch")
    rewards = raw.get("rewards")
    if rewards is not None and not isinstance(rewards, dict):
        raise ValueError("Invalid official reward object")
    result["raw_reward"] = (rewards or {}).get("reward")
    result["failure_reason"] = raw.get("error") or raw.get("verifier_error") or (
        "missing_reward" if result["raw_reward"] is None else
        "verifier_failure" if result["raw_reward"] != 1 else None)
    agent_timed_out = "timeout" in str(raw.get("error_category"))
    if interrupted or agent_timed_out or "timeout" in str(raw.get("verifier_error_category")):
        result["failure_reason"] = "timeout"
    if agent_timed_out and dispatched:
        # Completion callbacks cannot prove that cancellation left no unmetered
        # request in flight. Preserve known calls separately, never total them as
        # a complete attempt cost after an agent timeout.
        result["measurement_error"] = "agent_timeout_usage_incomplete"
    metrics = raw.get("agent_result") or {}
    # Native ACP can omit internal compaction calls; use the all-call proxy only.
    if metrics.get("usage_source") == "provider_response" and not interrupted and not agent_timed_out:
        result.update(usage_kind="provider_reported", **{
            dest: metrics.get(src) for dest, src in (
                ("input_tokens", "n_input_tokens"), ("output_tokens", "n_output_tokens"),
                ("cache_read_tokens", "n_cache_read_tokens"), ("cache_write_tokens", "n_cache_creation_tokens"))})
        if metrics.get("price_source") and metrics.get("cost_usd") is not None:
            result.update(estimated_cost_usd=metrics["cost_usd"],
                          cost_source="benchflow_" + metrics["price_source"] + "_estimate")
    elif not dispatched:
        result.update(input_tokens=0, output_tokens=0, cache_read_tokens=0, cache_write_tokens=0,
                      usage_kind="not_dispatched", actual_cost_usd=0,
                      cost_source="verified_before_provider_setup", model_api_calls=0)
    return result


def apply_request_accounting(result, accounting, evidence, *, native_agent_timeout):
    """Only a sealed complete inventory may settle a native agent timeout.

    This does not authorize continued execution after worker interruption,
    unknown cleanup or unverified settings; the caller checks those first.
    """
    settled = evidence.get("compaction", {}).get("agent_settled") is True
    if not evidence.get("settings_and_model_verified"):
        error = "effective_settings_or_model_unverified"
    elif not accounting.get("complete"):
        error = "request_accounting_incomplete"
    elif not (settled or native_agent_timeout):
        error = "agent_termination_unverified"
    else:
        error = None
    if error:
        result.update(measurement_error=error, usage_kind="unavailable", input_tokens=None,
                      output_tokens=None, cache_read_tokens=None, cache_write_tokens=None,
                      actual_cost_usd=None, estimated_cost_usd=None, cost_source="unavailable")
    else:
        result.update(measurement_error=None, usage_kind="provider_reported",
                      input_tokens=accounting["input_tokens"], output_tokens=accounting["output_tokens"],
                      cache_read_tokens=accounting["cache_read_tokens"], cache_write_tokens=None,
                      actual_cost_usd=None, estimated_cost_usd=accounting["cost_usd"],
                      cost_source="sealed_request_journal_provider_or_estimate",
                      model_api_calls=accounting["request_count"])
    return result


class SkillsBenchBenchmark:
    version = VERSION
    simulated_upper_bound = 0

    def __init__(self, config, tasks, output, *, evaluation_access=None):
        self.config = config
        self.evaluation_access = evaluation_access
        self.usd_upper_bound = config["attempt_spend_reservation_usd"]
        self.preflight = prepare_live(config, tasks, output / "live-preflight", require_credentials=True,
                                      evaluation_access=evaluation_access)
        if not self.preflight["ready"]:
            raise ValueError("Live preflight blocked: " + ", ".join(self.preflight["blockers"]))
        self.plans = {p["task_id"]: p for p in self.preflight["tasks"]}

    def evaluate(self, settings, task_id, seed, timeout_seconds, workdir):
        workdir.mkdir(mode=0o700, exist_ok=False)
        project = "pe6203-" + uuid.uuid4().hex
        plan = self.plans[task_id]
        request = {"live": self.config, "task_id": task_id, "settings": settings,
                   "evaluation_seed": seed, "provider_seed_controlled": False,
                   "project": project, "plan": plan}
        if getattr(self, "evaluation_access", None) is not None:
            request["evaluation_access"] = self.evaluation_access
        if getattr(self, "controlled_timeout_diagnostic", None) is not None:
            request["controlled_timeout_diagnostic"] = self.controlled_timeout_diagnostic
        (workdir / "request.json").write_text(canonical_json(request))
        (workdir / "settings.json").write_text(canonical_json(settings))
        env = isolated_env(workdir / "home", self.config["api_key_env"])
        if getattr(self, "diagnostic_spend_guard", None) is not None:
            env["PE6203_DIAGNOSTIC_SPEND_GUARD"] = canonical_json(self.diagnostic_spend_guard)
        before = time.monotonic()
        child = None
        interrupted = False
        interruption_reason = None
        process_cleanup_errors = []
        accounting_seconds = 0.0
        stdout = stderr = ""
        try:
            child = subprocess.Popen([runtime_python(self.config), "-m", "evaluation.live_worker", "run", str(workdir)],
                                     cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, start_new_session=True)
            # The campaign passes remaining method time; native phase limits stay intact.
            outer = min(plan["lifecycle_timeout_seconds"], timeout_seconds)
            try:
                stdout, stderr = child.communicate(timeout=outer)
            except (subprocess.TimeoutExpired, KeyboardInterrupt) as exc:
                interrupted = True
                interruption_reason = "cancelled" if isinstance(exc, KeyboardInterrupt) else "timeout"
                process_cleanup_errors.extend(stop_process(child))
                stdout, stderr = child.communicate(timeout=5)
        finally:
            if child is not None:
                process_cleanup_errors.extend(stop_process(child))
            cleanup = cleanup_project(project, env)
            (workdir / "cleanup.json").write_text(canonical_json(cleanup))
            secret = env.get(self.config["api_key_env"])
            for name, value in (("stdout", stdout), ("stderr", stderr)):
                (workdir / f"worker.{name}.log").write_text(value.replace(secret, "[REDACTED]") if secret else value)
        elapsed = time.monotonic() - before
        raw_path = workdir / "benchflow-result.json"
        raw = read_json(raw_path) if raw_path.exists() else None
        dispatched = (workdir / "provider-setup-started").exists()
        # A killed worker without its setup marker does not prove no requests were sent.
        result = normalize_result(raw, task_id, self.config["model"], elapsed,
                                  dispatched=dispatched or interrupted, interrupted=interrupted)
        if interruption_reason:
            result["failure_reason"] = interruption_reason
        if not cleanup["verified"]:
            result["measurement_error"] = "cleanup_unverified"
        elif process_cleanup_errors:
            result.update(measurement_error="process_cleanup_unverified", usage_kind="unavailable",
                          input_tokens=None, output_tokens=None, cache_read_tokens=None,
                          cache_write_tokens=None, actual_cost_usd=None, estimated_cost_usd=None,
                          cost_source="unavailable")
        elif interrupted:
            result["measurement_error"] = "worker_interrupted"
        elif child is None or child.returncode != 0:
            result["measurement_error"] = "worker_failed"
        elif dispatched:
            attestation = workdir / "execution-evidence.json"
            evidence = read_json(attestation) if attestation.exists() else {}
            if self.config.get("accounting_policy") == "request_journal_v1":
                from .request_accounting import reconcile_requests
                accounting = reconcile_requests(workdir, env.get(self.config["api_key_env"]))
                accounting_seconds = accounting["reconciliation_wall_seconds"]
                apply_request_accounting(result, accounting, evidence,
                    native_agent_timeout=bool(raw and "timeout" in str(raw.get("error_category"))))
            elif not evidence.get("settings_and_model_verified"):
                result["measurement_error"] = "effective_settings_or_model_unverified"
            if self.config.get("accounting_policy") != "request_journal_v1":
                normally_settled = evidence.get("compaction", {}).get("agent_settled") is True
                if not normally_settled:
                    result["measurement_error"] = result.get("measurement_error") or "agent_termination_unverified"
                usage_path = workdir / "provider-calls.json"
                usage = audit_usage_records(read_json(usage_path)) if usage_path.exists() else {"complete": False}
                if (not usage["complete"] or not normally_settled
                        or result.get("measurement_error") == "agent_timeout_usage_incomplete"):
                    result.update(measurement_error=result.get("measurement_error") or "incomplete_all_call_usage", usage_kind="unavailable",
                                  input_tokens=None, output_tokens=None, cache_read_tokens=None,
                                  cache_write_tokens=None, estimated_cost_usd=None, cost_source="unavailable")
                else:
                    result["model_api_calls"] = usage["model_api_calls"]
                    if any(result[k] != usage[k] for k in ("input_tokens", "output_tokens")):
                        result["measurement_error"] = "usage_aggregate_mismatch"
                    result["estimated_cost_usd"] = usage["estimated_cost_usd"]
                    result["cost_source"] = "litellm_all_call_estimate"
        elapsed = time.monotonic() - before
        result["wall_time_seconds"] = elapsed
        (workdir / "execution.json").write_text(canonical_json({
            "worker_exit_code": child.returncode if child else None, "interrupted": interrupted,
            "process_cleanup_errors": process_cleanup_errors,
            "accounting_wall_time_seconds": accounting_seconds,
            "cleanup_verified": cleanup["verified"], "elapsed_seconds": elapsed}))
        return result
