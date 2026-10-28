"""Pinned BenchFlow task environments with an additive, fixed Pi installation."""

import asyncio
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
from urllib.parse import urlsplit

import yaml

from pilot.config import ROOT, PINS, canonical_json, digest
from .telemetry import metering_record
from benchflow.agents.registry import get_agent, register_agent
from benchflow.rollout_planes import DefaultRolloutPlanes
from benchflow.sandbox.docker import DockerSandbox
from benchflow.task.task import Task


def task_path(task_id, live=None, evaluation_access=None):
    # Heldout access requires a separately frozen evaluator capability.
    from evaluation.panels import authorize_tasks
    authorize_tasks(live or {}, [task_id], evaluation_access)
    path = ROOT / "third_party/skillsbench/tasks" / task_id
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Task must be a local regular directory")
    return path


def task_files(path):
    # Do not load oracle solutions. Only these inputs are staged or fingerprinted.
    files = {}
    for name in ("task.md", "task.toml", "instruction.md", "environment", "verifier", "tests"):
        entry = path / name
        for p in sorted(entry.rglob("*")) if entry.is_dir() else [entry]:
            if p.is_symlink():
                raise ValueError(f"Task symlink is not supported: {p.relative_to(path)}")
            if p.is_file():
                files[str(p.relative_to(path))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


def compose_for_task(path):
    """Preserve task services/builds; remove the pinned task's unrelated GCloud mount."""
    source = path / "environment/docker-compose.yaml"
    if not source.exists():
        return {"services": {"main": {}}}, []
    document = yaml.safe_load(source.read_text())
    removed = []
    for name, service in document.get("services", {}).items():
        if any(service.get(k) for k in ("privileged", "devices", "container_name", "network_mode", "pid")):
            raise ValueError(f"Unsupported host-dependent Compose service: {name}")
        if service.get("ports"):
            raise ValueError("Host-published task ports must be reviewed before running")
        safe = []
        for volume in service.get("volumes", []):
            if volume == "${HOME}/.config/gcloud:/root/.config/gcloud:ro":
                removed.append(volume)
                continue
            # The fixed validation compose uses only BenchFlow's owned log mounts.
            if not isinstance(volume, str) or not volume.startswith(("${HOST_VERIFIER_LOGS_PATH", "${HOST_AGENT_LOGS_PATH", "${HOST_ARTIFACTS_PATH")):
                raise ValueError(f"Unreviewed task host mount: {name}")
            safe.append(volume)
        service["volumes"] = safe
        environment = service.get("environment", [])
        if isinstance(environment, list):
            service["environment"] = [e for e in environment if not e.startswith((
                "GOOGLE_APPLICATION_CREDENTIALS=", "CLAUDE_CODE_USE_VERTEX=",
                "CLOUD_ML_REGION=", "ANTHROPIC_VERTEX_PROJECT_ID="))]
    if any(v.get("external") for v in document.get("volumes", {}).values() if isinstance(v, dict)):
        raise ValueError("External task volumes are not supported")
    return document, removed


def plan_task(task_id, live, evaluation_access=None):
    path = task_path(task_id, live, evaluation_access)
    task = Task(path)
    cfg, env = task.config, task.config.environment
    if str(env.os) != "linux" or env.gpus or env.tpu or env.mcp_servers or env.docker_image:
        raise ValueError(f"Unsupported environment capability for {task_id}")
    if str(env.network_mode) not in ("public", "no-network"):
        raise ValueError("Allowlist networking needs a separately implemented policy")
    if env.env or cfg.verifier.env:
        raise ValueError("Task-specific secret environment requires an explicit forwarding policy")
    if not (path / "environment/Dockerfile").is_file():
        raise ValueError("Task must provide its native Dockerfile")
    compose, removed = compose_for_task(path)
    skills = sorted(str(p.relative_to(path)) for p in (path / "environment/skills").glob("*/SKILL.md"))
    if live["skill_mode"] == "with-skill" and not skills:
        raise ValueError("with-skill requires bundled task skills")
    limits = {"agent": float(cfg.agent.timeout_sec), "verifier": float(cfg.verifier.timeout_sec),
              "build": float(env.build_timeout_sec)}
    if any(v <= 0 for v in limits.values()):
        raise ValueError("Task phase timeouts must be positive")
    return {"task_id": task_id, "file_hashes": task_files(path), "timeouts": limits,
            "lifecycle_timeout_seconds": sum(limits.values()) + live["setup_timeout_seconds"] + live["cleanup_timeout_seconds"] + 60,
            "environment": env.model_dump(mode="json"), "skills": skills,
            "skill_mode": live["skill_mode"], "services": sorted(compose["services"]),
            "removed_host_mounts": removed, "oracle_access": False,
            "network_enforcement": "agent_uid_proxy_only" if not env.allow_internet else "task_public"}


def stage_task(plan, live, output, evaluation_access=None):
    source = task_path(plan["task_id"], live, evaluation_access)
    if task_files(source) != plan["file_hashes"]:
        raise ValueError("Task changed since live preflight")
    path = output / "task" / plan["task_id"]
    path.mkdir(parents=True)
    for relative in plan["file_hashes"]:
        dest = path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, dest)
    # Tag references are checked against the full local image ID before every build.
    image = live["runtime_image"]
    identity = subprocess.check_output(["docker", "image", "inspect", image, "--format", "{{.Id}}"], text=True, timeout=20).strip()
    tag = "pe6203-pinned-runtime:" + identity.removeprefix("sha256:")
    subprocess.run(["docker", "tag", identity, tag], check=True, capture_output=True, timeout=20)
    dockerfile = path / "environment/Dockerfile"
    with dockerfile.open("a") as f:
        f.write(f"\n# PE6203: fixed additive agent runtime; native task layers above are retained.\n"
                f"USER root\nCOPY --from={tag} /opt/benchflow/ /opt/benchflow/\n"
                f"COPY --from={tag} /opt/pe6203/ /opt/pe6203/\n"
                "RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "
                "python3 bash ca-certificates curl git sudo procps ripgrep iptables "
                "&& rm -rf /var/lib/apt/lists/*\n"
                "RUN /opt/benchflow/bin/pi --version && test -f /opt/benchflow/js-agents/lib/node_modules/pi-acp/dist/index.js\n")
    compose, removed = compose_for_task(source)
    main = compose["services"].setdefault("main", {})
    if plan["network_enforcement"] == "agent_uid_proxy_only":
        main["cap_add"] = ["NET_ADMIN"]
    (path / "environment/docker-compose.yaml").write_text(yaml.safe_dump(compose))
    (output / "staging.json").write_text(canonical_json({
        "source": plan, "runtime_image_id": identity, "runtime_build_tag": tag,
        "staged_files": task_files(path), "removed_host_mounts": removed}))
    return path


class TaskSandbox(DockerSandbox):
    async def start(self, force_build):
        # Pinned DockerSandbox doesn't pass build_timeout_sec to compose.
        await asyncio.wait_for(super().start(force_build), timeout=self.task_env_config.build_timeout_sec)
        cid = await self._main_container_id()
        if not cid:
            raise RuntimeError("Task container missing after startup")
        observation = await self._docker_cli(["inspect", "--format",
            '{"image_id":{{json .Image}},"cpu_limit_nanos":{{.HostConfig.NanoCpus}},"memory_limit_bytes":{{.HostConfig.Memory}}}', cid])
        (self.rollout_paths.rollout_dir / "environment-image.json").write_text(observation.stdout)

    async def stop(self, delete):
        # Preserve cached task/runtime images, remove volumes as well as containers.
        await self._run_docker_compose_command(["down", "--volumes", "--remove-orphans", "-t", "5"], timeout_sec=45)


class TaskPlanes(DefaultRolloutPlanes):
    def __init__(self, output, plan, live):
        self.output, self.plan, self.live = output, plan, live

    async def stop_provider_runtime(self, runtime):
        # Rollout.cleanup has already disconnected the agent. Allow callbacks
        # from already-billed requests to arrive before killing the proxy.
        # A quiet callback file alone does not prove that no request is pending.
        if self.live.get('accounting_policy') == 'request_journal_v1':
            from .request_drain import drain_requests
            await drain_requests(self.output)
        return await super().stop_provider_runtime(runtime)

    def create_environment(self, environment, task, task_path, rollout_name, rollout_paths, **kwargs):
        if environment != "docker":
            raise ValueError("Live evaluator currently supports Docker")
        cfg = task.config.environment.model_copy(deep=True)
        # Provider connectivity exists during provisioning. Before launching Pi,
        # no-network tasks get an owner-based firewall allowing only the proxy.
        cfg.allow_internet = True
        cache_id = digest({"files": self.plan["file_hashes"], "image": self.live["runtime_image"],
                           "skill_mode": self.live["skill_mode"], "adapter": Path(__file__).read_text()})[:12]
        return TaskSandbox(environment_dir=task_path / "environment",
                           environment_name=f"pe6203-{task_path.name}-{cache_id}", session_id=rollout_name,
                           rollout_paths=rollout_paths, task_env_config=cfg)

    async def ensure_litellm_runtime(self, *args, **kwargs):
        (self.output / "provider-setup-started").write_text("Provider calls may occur after this point.\n")
        journal_enabled = self.live.get("accounting_policy") == "request_journal_v1"
        from benchflow.providers import litellm_runtime
        from .request_accounting import callback_source, proxy_config, seal_journal
        original_source = litellm_runtime.callback_module_source
        original_config = litellm_runtime.litellm_proxy_config
        try:
            # Each worker owns exactly one proxy. Extend its generated callback
            # module without modifying the pinned third-party checkout.
            if journal_enabled:
                litellm_runtime.callback_module_source = lambda: callback_source(original_source(), self.output)
                litellm_runtime.litellm_proxy_config = lambda route, **kw: proxy_config(original_config, route, **kw)
            env, runtime = await super().ensure_litellm_runtime(*args, **kwargs)
        finally:
            litellm_runtime.callback_module_source = original_source
            litellm_runtime.litellm_proxy_config = original_config
        # Pinned HostLiteLLMProcess loads callbacks immediately before deleting
        # its temp directory. Save metering fields at that seam, after proxy exit.
        server = getattr(runtime, "server", None)
        if server is None or not callable(getattr(server, "_load_callback_log", None)):
            await self.stop_provider_runtime(runtime)
            raise RuntimeError("Unsupported provider metering runtime")
        original_loader = server._load_callback_log
        def load_and_capture():
            original_loader()
            rows = []
            if server.log_path.exists():
                for line in server.log_path.read_text().splitlines():
                    record = json.loads(line)
                    rows.append(metering_record(record))
            (self.output / "provider-calls.json").write_text(canonical_json(rows))
            if journal_enabled:
                seal_journal(self.output, server.process.poll())
        server._load_callback_log = load_and_capture
        if self.plan["network_enforcement"] == "agent_uid_proxy_only":
            # Keep the runtime reference recoverable if firewall installation fails.
            try:
                env = await self.restrict_agent_network(kwargs["sandbox"], env)
            except BaseException:
                await self.stop_provider_runtime(runtime)
                raise
        return env, runtime

    async def restrict_agent_network(self, sandbox, env):
        endpoint = urlsplit(env["BENCHFLOW_PROVIDER_BASE_URL"])
        if endpoint.scheme != "http" or not endpoint.port:
            raise ValueError("Expected local HTTP usage proxy")
        probe = await sandbox.exec("python3 -c " + shlex.quote(
            f"import socket; print(socket.gethostbyname({endpoint.hostname!r}))"), user="root", timeout_sec=10)
        import ipaddress
        ip = str(ipaddress.IPv4Address(probe.stdout.strip()))
        env = dict(env, BENCHFLOW_PROVIDER_BASE_URL=f"http://{ip}:{endpoint.port}{endpoint.path}")
        command = (
            "set -eu; uid=$(id -u agent); "
            "iptables -N PE6203_AGENT; "
            f"iptables -A PE6203_AGENT -d {ip} -p tcp --dport {endpoint.port} -j ACCEPT; "
            "iptables -A PE6203_AGENT -j REJECT; "
            "iptables -I OUTPUT 1 -m owner --uid-owner \"$uid\" -j PE6203_AGENT; "
            "ip6tables -I OUTPUT 1 -m owner --uid-owner \"$uid\" -j REJECT; "
            "iptables -S PE6203_AGENT; ip6tables -S OUTPUT")
        result = await sandbox.exec(command, user="root", timeout_sec=15)
        if result.return_code:
            raise RuntimeError("No-network firewall setup failed")
        (self.output / "network-policy.log").write_text(result.stdout)
        return env


def register_pi():
    original, _ = get_agent("pi-acp")
    registration = asdict(original)
    registration.update(name="pe6203-pi-live", description="Pinned Pi for task-native SkillsBench HPO",
                        install_cmd="test -x /opt/benchflow/bin/pi && test -x /opt/benchflow/bin/pi-acp",
                        launch_cmd="python3 /opt/pe6203/launch.py")
    register_agent(**registration)
