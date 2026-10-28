"""Project adapters for the pinned BenchFlow runtime."""

from benchflow.rollout_planes import DefaultRolloutPlanes


class SharedImageSandbox:
    """Delegate the sandbox protocol while retaining the reviewed local image."""

    def __init__(self, sandbox):
        self._sandbox = sandbox

    def __getattr__(self, name):
        return getattr(self._sandbox, name)

    async def stop(self, delete):
        # Pinned DockerSandbox.stop(delete=True) uses `compose down --rmi all`,
        # which deletes our prebuilt image as well as the trial container.
        # delete=False still removes containers/networks; this sanity task has
        # only host bind mounts, no named volumes to clean up separately.
        await self._sandbox.stop(delete=False)


class PilotPlanes(DefaultRolloutPlanes):
    def create_environment(self, environment, *args, **kwargs):
        if environment != "docker":
            raise ValueError("The reviewed pilot supports Docker only")
        return SharedImageSandbox(super().create_environment(environment, *args, **kwargs))
