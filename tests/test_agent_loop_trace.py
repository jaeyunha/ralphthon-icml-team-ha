import hashlib
import json
import os
import subprocess
import shutil

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "engine/loops/agent-loop.sh"


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run_loop(
    tmp_path: Path, *, attempt: int, mode: str, trace: bool = True
) -> subprocess.CompletedProcess[str]:
    repo = tmp_path / "repo"
    (repo / "engine/loops").mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "engine/loops/invocation_trace.py", repo / "engine/loops/invocation_trace.py"
    )
    workspace = tmp_path / "workspace"
    role = write(repo / "roles/reviewer/PROMPT.base.md", "role\n")
    phase = write(repo / "roles/reviewer/phases/draft/PROMPT.md", "phase\n")
    policy = write(repo / "policy.md", "policy\n")
    rubric = write(repo / "rubric.md", "rubric\n")
    context = write(repo / "task.json", '{"task":"x"}\n')
    schema = write(repo / "schema.json", '{"type":"object","required":["value"]}\n')
    fake = write(
        repo / "fake-agent.sh",
        "#!/usr/bin/env bash\nset -eu\ncat >/dev/null\n"
        'if [ "$FAKE_MODE" = bad ]; then printf \'{}\\n\' > "$RALPH_OUTPUT_ARTIFACT"; else printf \'{"value":1}\\n\' > "$RALPH_OUTPUT_ARTIFACT"; fi\n'
        "printf '<promise>NEXT</promise>\\n'\n",
    )
    fake.chmod(0o755)
    artifact = workspace / "artifact.json"
    command = [
        str(LOOP),
        "--repo-root",
        str(repo),
        "--agent-id",
        "agent-a",
        "--role",
        "reviewer",
        "--phase",
        "draft",
        "--workspace",
        str(workspace),
        "--task-context",
        str(context),
        "--output-schema",
        str(schema),
        "--artifact",
        str(artifact),
        "--policy",
        str(policy),
        "--rubric",
        str(rubric),
        "--role-prompt",
        str(role),
        "--phase-prompt",
        str(phase),
        "--agent-command",
        str(fake),
        "--timeout",
        "5",
    ]
    env = os.environ | {"FAKE_MODE": mode}
    if trace:
        env |= {
            "AGENT_LOOP_V2_TRACE_DIR": str(
                tmp_path / "traces/invocations/inv-a/attempts" / str(attempt)
            ),
            "AGENT_LOOP_INVOCATION_ID": "inv-a",
            "AGENT_LOOP_INVOCATION_ATTEMPT": str(attempt),
            "AGENT_LOOP_CAUSATION_EVENT_ID": "cause-1",
            "AGENT_LOOP_EXECUTION_STARTED_EVENT_ID": "started-1",
        }
    return subprocess.run(command, text=True, capture_output=True, env=env, check=False)


def test_v2_trace_preserves_attempts_and_is_idempotent(tmp_path: Path) -> None:
    failed = run_loop(tmp_path, attempt=1, mode="bad")
    assert failed.returncode == 20
    succeeded = run_loop(tmp_path, attempt=2, mode="good")
    assert succeeded.returncode == 0
    retry = run_loop(tmp_path, attempt=2, mode="good")
    assert retry.returncode == 0, retry.stderr

    root = tmp_path / "traces/invocations/inv-a/attempts"
    first, second = root / "1", root / "2"
    assert first != second and first.is_dir() and second.is_dir()
    assert (first / "validation-feedback.txt").read_text(encoding="utf-8")
    assert (first / "candidate-artifact").read_bytes() == b"{}\n"
    assert b"EXACT REOPEN FEEDBACK" in (second / "prompt.txt").read_bytes()
    for directory in (first, second):
        manifest = json.loads((directory / "invocation-manifest.json").read_text(encoding="utf-8"))
        assert manifest["causation_event_id"] == "cause-1"
        assert manifest["execution_started_event_id"] == "started-1"
        for entry in manifest["files"]:
            body = (directory / entry["path"]).read_bytes()
            assert entry["sha256"] == "sha256:" + hashlib.sha256(body).hexdigest()
    assert (second / "invocation-result.json").read_bytes() == (
        tmp_path / "workspace/phases/draft/invocation-result.json"
    ).read_bytes()


def test_legacy_loop_does_not_create_trace(tmp_path: Path) -> None:
    result = run_loop(tmp_path, attempt=1, mode="good", trace=False)
    assert result.returncode == 0
    assert not (tmp_path / "traces").exists()
    assert (tmp_path / "workspace/phases/draft/stdout.log").read_text(
        encoding="utf-8"
    ) == "<promise>NEXT</promise>\n"
