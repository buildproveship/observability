"""Bounded Docker Compose calls pinned to the local daemon socket."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DAEMON = "--host=unix:///var/run/docker.sock"
# Inherited selectors that could point Docker at a remote daemon or other profiles.
_INHERITED_SELECTORS = frozenset(
    {
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "COMPOSE_PROFILES",
    }
)


def local_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the current environment without remote Docker or profile selectors."""
    env = {k: v for k, v in os.environ.items() if k not in _INHERITED_SELECTORS}
    env.update(extra or {})
    return env


def _docker() -> str:
    path = shutil.which("docker")
    if path is None:
        raise FileNotFoundError("docker CLI not found on PATH")
    return path


@dataclass(frozen=True)
class ComposeProject:
    """One fixed Compose project on the local daemon; it owns only its resources."""

    name: str
    files: tuple[Path, ...]
    profiles: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)

    def command(self, *args: str) -> list[str]:
        command = [_docker(), LOCAL_DAEMON, "compose", "--project-name", self.name]
        for file in self.files:
            command += ["-f", str(file)]
        for profile in self.profiles:
            command += ["--profile", profile]
        return [*command, *args]

    def run(self, *args: str, timeout: float = 60, capture: bool = False) -> str:
        """Run one bounded `docker compose` command; raise on failure or timeout."""
        result = subprocess.run(  # noqa: S603 -- fixed argv list, no shell
            self.command(*args),
            cwd=ROOT,
            env=local_env(self.env),
            check=True,
            timeout=timeout,
            capture_output=capture,
            text=True,
        )
        return result.stdout or ""


def inspect(container: str) -> Any:
    """Return `docker inspect` data for one container on the local daemon."""
    output = subprocess.check_output(  # noqa: S603 -- fixed argv list, no shell
        [_docker(), LOCAL_DAEMON, "inspect", container], env=local_env(), timeout=10
    )
    return json.loads(output)[0]
