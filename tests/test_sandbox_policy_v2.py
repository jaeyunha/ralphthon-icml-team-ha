from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.validators.sandbox.runtime import (
    DockerSandbox,
    ReadOnlyInput,
    SandboxRequest,
    _container_name,
    _hash_path,
)


DIGEST_IMAGE = "example.invalid/validator@sha256:" + "a" * 64


def test_v2_requires_digest_pinned_image() -> None:
    with pytest.raises(ValueError, match="pinned"):
        SandboxRequest(image="validator:latest", argv=("python", "check.py"), policy_version=2)

    request = SandboxRequest(image=DIGEST_IMAGE, argv=("python", "check.py"), policy_version=2)
    assert request.image == DIGEST_IMAGE


def test_v2_command_is_pull_never_and_hardened(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    request = SandboxRequest(
        image=DIGEST_IMAGE,
        argv=("python", "/inputs/source"),
        inputs=(ReadOnlyInput("source", source),),
        policy_version=2,
    )

    command = DockerSandbox("docker").build_command(request, "deterministic-name")

    assert command[:7] == [
        "docker",
        "run",
        "--rm",
        "--pull",
        "never",
        "--name",
        "deterministic-name",
    ]
    assert ["--network", "none"] == command[
        command.index("--network") : command.index("--network") + 2
    ]
    assert "--read-only" in command
    assert ["--cap-drop", "ALL"] == command[
        command.index("--cap-drop") : command.index("--cap-drop") + 2
    ]
    assert ["--security-opt", "no-new-privileges"] == command[
        command.index("--security-opt") : command.index("--security-opt") + 2
    ]


def test_pinned_image_digest_verifies_repo_digest_membership() -> None:
    class FakeDocker(DockerSandbox):
        def __init__(self, stdout: str) -> None:
            super().__init__("docker")
            self.stdout = stdout

        def _run_control(self, argv, timeout=20.0):
            return SimpleNamespace(returncode=0, stdout=self.stdout, stderr="")

    expected = "sha256:" + "a" * 64
    image = f"example.invalid/validator@{expected}"
    assert FakeDocker(f'["example.invalid/validator@{expected}"]').image_digest(image) == expected
    assert FakeDocker("[]").image_digest(image) is None


def test_container_identity_and_source_hash_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("print('one')\n", encoding="utf-8")
    request = SandboxRequest(
        image=DIGEST_IMAGE,
        argv=("python", "/inputs/source"),
        inputs=(ReadOnlyInput("source", source),),
        policy_version=2,
    )
    first_hash = _hash_path(source)
    first_name = _container_name(request, {"source": first_hash})

    assert first_name == _container_name(request, {"source": first_hash})
    source.write_text("print('two')\n", encoding="utf-8")
    second_hash = _hash_path(source)
    assert second_hash != first_hash
    assert _container_name(request, {"source": second_hash}) != first_name


def test_source_hash_rejects_links_and_hardlinks(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("print('ok')\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="symbolic"):
        _hash_path(link)

    hardlink = tmp_path / "hardlink.py"
    hardlink.hardlink_to(source)
    with pytest.raises(ValueError, match="unique regular"):
        _hash_path(source)
