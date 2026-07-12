from __future__ import annotations

from pathlib import Path

import pytest

from engine.loops.egress_broker import EgressDenied, EndpointPolicy
from engine.loops.sandbox_profiles import SandboxPolicyError, SandboxUnavailable, StagedPath
from engine.loops.sterile_launcher import LaunchDenied, LaunchRequest, SterileLauncher


def staged_tool(tmp_path: Path) -> tuple[Path, Path, tuple[StagedPath, ...]]:
    tool = tmp_path / "tool"
    tool.write_text("#!/bin/sh\nexit 0\n")
    tool.chmod(0o700)
    input_file = tmp_path / "input.txt"
    input_file.write_text("only declared data")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return tool, workspace, (StagedPath(tool, "/tool"), StagedPath(input_file, "/inputs/input.txt"))


def launcher(tool: Path) -> SterileLauncher:
    return SterileLauncher({str(tool.resolve()): ("--fixed",)})


def test_launcher_scrubs_proxy_credentials_and_all_inherited_file_descriptors(
    tmp_path: Path,
) -> None:
    tool, workspace, paths = staged_tool(tmp_path)
    request = LaunchRequest(
        str(tool),
        ("--fixed",),
        workspace,
        paths,
        {
            "HTTPS_PROXY": "http://secret",
            "AWS_SECRET_ACCESS_KEY": "secret",
            "SSH_AUTH_SOCK": "/sock",
            "LANG": "C",
        },
        (0, 1, 2),
    )
    plan = launcher(tool).plan(request, platform_name="Linux", which=lambda _: "/usr/bin/bwrap")
    assert plan.environment == {"LANG": "C"}
    assert plan.close_fds and plan.pass_fds == ()
    assert "secret" not in plan.evidence_hash
    with pytest.raises(LaunchDenied, match="file_descriptor"):
        launcher(tool).plan(
            LaunchRequest(str(tool), ("--fixed",), workspace, paths, inherited_fds=(3,)),
            platform_name="Linux",
            which=lambda _: "/usr/bin/bwrap",
        )


def test_linux_plan_has_private_network_and_only_declared_path_grants(tmp_path: Path) -> None:
    tool, workspace, paths = staged_tool(tmp_path)
    plan = launcher(tool).plan(
        LaunchRequest(str(tool), ("--fixed",), workspace, paths),
        platform_name="Linux",
        which=lambda _: "/usr/bin/bwrap",
    )
    assert plan.sandbox.enforcement == "bubblewrap"
    assert "--unshare-net" in plan.sandbox.argv
    assert "--ro-bind" in plan.sandbox.argv
    assert "/inputs/input.txt" in plan.sandbox.argv
    assert plan.sandbox.argv[-2:] == ("/tool", "--fixed")
    with pytest.raises(SandboxPolicyError, match="explicitly staged"):
        launcher(tool).plan(
            LaunchRequest(str(tool), ("--fixed",), workspace, (paths[1],)),
            platform_name="Linux",
            which=lambda _: "/usr/bin/bwrap",
        )


def test_unsupported_or_missing_isolation_fails_closed(tmp_path: Path) -> None:
    tool, workspace, paths = staged_tool(tmp_path)
    request = LaunchRequest(str(tool), ("--fixed",), workspace, paths)
    with pytest.raises(SandboxUnavailable, match="unsupported"):
        launcher(tool).plan(request, platform_name="Windows", which=lambda _: None)
    with pytest.raises(SandboxUnavailable, match="bwrap"):
        launcher(tool).plan(request, platform_name="Linux", which=lambda _: None)


def test_unrestricted_commands_and_sandbox_bypass_flags_are_denied(tmp_path: Path) -> None:
    tool, workspace, paths = staged_tool(tmp_path)
    with pytest.raises(LaunchDenied, match="allowlisted"):
        launcher(tool).plan(
            LaunchRequest(str(tool), ("--other",), workspace, paths),
            platform_name="Linux",
            which=lambda _: "/usr/bin/bwrap",
        )
    with pytest.raises(LaunchDenied, match="bypass"):
        launcher(tool).plan(
            LaunchRequest(
                str(tool),
                ("--fixed", "--dangerously-bypass-approvals-and-sandbox"),
                workspace,
                paths,
            ),
            platform_name="Linux",
            which=lambda _: "/usr/bin/bwrap",
        )


def public_resolver(host: str, port: int) -> tuple[str, ...]:
    assert host == "broker.example" and port == 443
    return ("93.184.216.34",)


def test_exact_broker_endpoint_accepts_only_the_configured_tls_endpoint() -> None:
    policy = EndpointPolicy("https://broker.example/v1", resolver=public_resolver)
    assert policy.authorize("https://broker.example/v1") == ("93.184.216.34",)
    options = policy.connection_options("https://broker.example/v1")
    assert options["allow_redirects"] is False and options["proxy"] is None
    policy.verify_tls(peer_hostname="broker.example", tls_version="TLSv1.3")


@pytest.mark.parametrize(
    "url",
    [
        "http://broker.example/v1",
        "https://broker.example:444/v1",
        "https://other.example/v1",
        "ws://broker.example/v1",
        "https://broker.example/other",
    ],
)
def test_broker_rejects_direct_or_alternate_targets(url: str) -> None:
    policy = EndpointPolicy("https://broker.example/v1", resolver=public_resolver)
    with pytest.raises(EgressDenied):
        policy.authorize(url)


def test_broker_rejects_private_metadata_and_rebinding_dns_targets() -> None:
    private = EndpointPolicy("https://broker.example/v1", resolver=lambda *_: ("169.254.169.254",))
    with pytest.raises(EgressDenied, match="private"):
        private.authorize("https://broker.example/v1")
    answers = iter((("93.184.216.34",), ("93.184.216.35",)))
    rebinding = EndpointPolicy("https://broker.example/v1", resolver=lambda *_: next(answers))
    with pytest.raises(EgressDenied, match="rebinding"):
        rebinding.authorize("https://broker.example/v1")
