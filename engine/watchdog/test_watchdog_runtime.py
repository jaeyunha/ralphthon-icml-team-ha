#!/usr/bin/env python3
import argparse
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

from engine.watchdog.watchdog_runtime import Watchdog
from jsonschema import Draft202012Validator, FormatChecker

HERE = Path(__file__).resolve().parent
WATCHDOG = HERE / "committee-watchdog.sh"
AGENT_LOOP = HERE.parent / "loops/agent-loop.sh"
CONTRACT_ADAPTER = HERE / "contracts-adapter.sh"
SCHEMA_ROOT = HERE.parents[1] / "packages/schemas/schemas"
VALIDATE_RUN = HERE.parents[1] / "scripts/validate-run.sh"
os.environ.setdefault("WATCHDOG_ALLOW_LEGACY_RESULTS", "1")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def runner(path, body):
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)


def executable(path, body):
    path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
    path.chmod(0o755)


class WatchdogTest(unittest.TestCase):
    def invoke(self, run, fake, *extra):
        return subprocess.run(
            [str(WATCHDOG), "--run-dir", str(run), "--runner", str(fake), "--poll-seconds", "0.02", *extra],
            text=True, capture_output=True, timeout=10,
        )

    def agent_loop_config(self, run, fake):
        policy = run / "policy.md"; policy.write_text("Use only the manifest. End with one promise.\n", encoding="utf-8")
        rubric = run / "rubric.md"; rubric.write_text("Return a complete valid artifact.\n", encoding="utf-8")
        role_prompt = run / "role.md"; role_prompt.write_text("Preserve the logical identity.\n", encoding="utf-8")
        phase_prompt = run / "phase.md"; phase_prompt.write_text("Write hello.json.\n", encoding="utf-8")
        task = run / "task.json"; write_json(task, {"task": "write hello"})
        schema = run / "hello.schema.json"
        write_json(schema, {"type": "object", "additionalProperties": False, "required": ["message"], "properties": {"message": {"const": "hello"}}})
        return {
            "initial_state": "AUTHOR_FINAL", "initial_backoff_seconds": 0, "max_backoff_seconds": 0,
            "phase_runs": [{
                "agent_id": "author", "role": "author", "phase": "final-followup", "gates": [],
                "task_context": str(task), "output_schema": str(schema), "policy": str(policy),
                "rubric": str(rubric), "role_prompt": str(role_prompt), "phase_prompt": str(phase_prompt),
                "agent_command": str(fake),
            }],
        }

    def assert_schema(self, path, schema_name):
        schema = json.loads((SCHEMA_ROOT / f"{schema_name}.schema.json").read_text())
        value = json.loads(path.read_text())
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def test_happy_path_initializes_workspace_and_completes(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "run_id": "happy", "initial_state": "REVIEWER_FOLLOWUP",
                "phase_runs": [{"agent_id": "reviewer-r2", "role": "reviewer", "phase": "followup", "gates": []}],
            })
            runner(fake, """import hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); a=p/'artifacts'/'validated'/'followup.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{\"ok\":true}')
h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads((run / ".watchdog/status.json").read_text())
            self.assertEqual(status["status"], "SUCCESS")
            self.assertEqual(json.loads((run / "agents/reviewer-r2/identity.json").read_text())["agent_id"], "reviewer-r2")
            self.assertTrue((run / "agents/reviewer-r2/phases/followup/tasks.json").exists())
            self.assert_schema(run / ".watchdog/status.json", "watchdog-status")
            self.assert_schema(run / ".watchdog/run-budget.json", "run-budget")
            self.assert_schema(run / "watchdog-config.json", "watchdog-config")
            self.assert_schema(run / "agents/reviewer-r2/phases/followup/tasks.json", "phase-tasks")
            self.assert_schema(run / "agents/reviewer-r2/phases/followup/current-task-context.json", "task-context")
            self.assert_schema(run / "agents/reviewer-r2/score-history.json", "score-history")
            self.assert_schema(run / "agents/reviewer-r2/literature-registry.json", "literature-registry")
            self.assertEqual(json.loads((run / "agents/reviewer-r2/score-history.json").read_text())["entries"], [])
            self.assertEqual(json.loads((run / "agents/reviewer-r2/literature-registry.json").read_text())["entries"], [])

    def test_opt_in_held_supervisor_releases_only_after_v2_execution_event(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "run_id": "held-v2", "initial_state": "AUTHOR_REBUTTAL",
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": [], "held_supervisor_v2": True}],
            })
            runner(fake, """import hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); trace=pathlib.Path(os.environ['AGENT_LOOP_V2_TRACE_DIR']); (p/'released').write_text(os.environ['AGENT_LOOP_INVOCATION_ID']); a=p/'artifacts'/'validated'/'rebuttal.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}'); h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            args = argparse.Namespace(run_dir=str(run), config=None, runner=str(fake), once=True, poll_seconds=0.02, heartbeat_timeout_seconds=300.0)
            watchdog = Watchdog(args)
            try:
                watchdog.initialize()
                watchdog.start(watchdog.phases[0])
                watchdog.children[watchdog.phases[0]["key"]].wait(timeout=5)
            finally:
                watchdog.terminate_children()
                shutil.rmtree(run / ".watchdog.lock", ignore_errors=True)
            event = json.loads((run / "events-v2.ndjson").read_text())
            self.assertEqual(event["type"], "author.rebuttal.execution_started")
            self.assertTrue((run / "agents/author/phases/rebuttal/released").exists())
            prepared = next((run / ".watchdog/held-supervisor-v2").glob("*/spawn_prepared.json"))
            self.assertEqual(json.loads(prepared.read_text())["invocation_id"], event["payload"]["invocation_id"])

    def test_workspace_core_documents_match_frozen_schemas(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "run_id": "schema-run", "initial_state": "REVIEWER_FOLLOWUP",
                "phase_runs": [{"agent_id": "reviewer-r2", "role": "reviewer", "phase": "followup", "gates": []}],
            })
            runner(fake, """import hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); a=p/'artifacts'/'validated'/'followup.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}')
h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            agent = run / "agents/reviewer-r2"
            self.assert_schema(agent / "identity.json", "identity")
            self.assert_schema(agent / "persona.json", "persona")
            self.assert_schema(agent / "role-state.json", "role-state")
            self.assert_schema(agent / "concern-ledger.json", "concern-ledger")
            self.assert_schema(agent / "question-ledger.json", "question-ledger")
            self.assert_schema(agent / "phases/followup/state.json", "phase-state")
            event_schema = json.loads((SCHEMA_ROOT / "event-envelope.schema.json").read_text())
            validator = Draft202012Validator(event_schema, format_checker=FormatChecker())
            for line in (run / "events.ndjson").read_text().splitlines():
                self.assertEqual(list(validator.iter_errors(json.loads(line))), [])
            sequence_state = json.loads((run / ".watchdog/event-sequence.state").read_text())
            self.assertEqual((sequence_state["schema_version"], sequence_state["run_id"]), (1, "schema-run"))
            self.assertEqual(sequence_state["last_sequence"], len((run / "events.ndjson").read_text().splitlines()))

    def test_contract_adapter_generates_hash_verified_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); workspace = run / "agents/reviewer-r1"; workspace.mkdir(parents=True)
            manifest = workspace / "allowed-inputs.json"
            command = [str(CONTRACT_ADAPTER), "generate-manifest", "--repo-root", str(HERE.parents[1]), "--workspace", str(workspace), "--agent-id", "reviewer-r1", "--role", "reviewer", "--phase", "initial-review", "--output", str(manifest)]
            generated = subprocess.run(command, text=True, capture_output=True, timeout=10)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            verified = subprocess.run([str(CONTRACT_ADAPTER), "verify-manifest", "--manifest", str(manifest)], text=True, capture_output=True, timeout=10)
            self.assertEqual(verified.returncode, 0, verified.stderr)
            self.assert_schema(manifest, "allowed-inputs")

    def test_watchdog_reads_flat_safety_from_frozen_run_config(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "config_version": 1, "run_id": "frozen-run", "mode": "live_submission", "review_start_time": "2026-07-11T00:00:00Z", "literature_cutoff": "2026-01-28T23:59:59-12:00", "submission_manifest_path": "submission-manifest.json", "reviewer_count": 3,
                "max_wall_clock_hours": 1, "max_budget_usd": 0, "max_author_restarts": 2, "max_discussion_rounds": 4, "no_progress_threshold": 2,
            })
            self.assert_schema(run / "run-config.json", "run-config")
            write_json(run / "watchdog-config.json", {
                "initial_state": "AUTHOR_REBUTTAL", "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": []}],
            })
            runner(fake, """import hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); a=p/'artifacts'/'validated'/'rebuttal.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}')
h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            identity = json.loads((run / "agents/author/identity.json").read_text())
            budget = json.loads((run / ".watchdog/run-budget.json").read_text())
            self.assertEqual(identity["run_id"], "frozen-run")
            self.assertEqual(budget["limits"]["max_author_restarts"], 2)
            self.assertEqual(budget["limits"]["no_progress_threshold"], 2)

    def test_agent_loop_uses_frozen_visibility_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"; run = Path(temp) / "run-1"; workspace = run / "agents/reviewer-r1"; phase = workspace / "phases/initial-review"
            (root / "shared").mkdir(parents=True); (root / "roles/reviewer/phases/initial-review").mkdir(parents=True); (root / "roles/reviewer/schemas").mkdir(parents=True); phase.mkdir(parents=True)
            (root / "shared/COMMON_AGENT_POLICY.md").write_text("Use the manifest and emit one promise.\n")
            (root / "shared/ICML_2026_REVIEW_RUBRIC.md").write_text("Produce a valid artifact.\n")
            (root / "roles/reviewer/PROMPT.base.md").write_text("Review independently.\n")
            (root / "roles/reviewer/phases/initial-review/PROMPT.md").write_text("Write hello.\n")
            write_json(root / "roles/reviewer/schemas/initial-review.schema.json", {"type": "object", "required": ["message"], "properties": {"message": {"const": "hello"}}})
            write_json(workspace / "persona.json", {"reviewer_id": "reviewer-r1"})
            task = phase / "current-task-context.json"; write_json(task, {"task": "hello"})
            artifact = phase / "artifacts/hello.json"; fake = Path(temp) / "fake-agent.sh"
            executable(fake, "python3 -c 'import sys; sys.stdin.read()'\nprintf '{\"message\":\"hello\"}\\n' > \"$RALPH_OUTPUT_ARTIFACT\"\nprintf '<promise>COMPLETE</promise>\\n'\n")
            command = [str(AGENT_LOOP), "--repo-root", str(root), "--agent-id", "reviewer-r1", "--role", "reviewer", "--phase", "initial-review", "--workspace", str(workspace), "--task-context", str(task), "--output-schema", str(root / "roles/reviewer/schemas/initial-review.schema.json"), "--artifact", str(artifact), "--manifest-generator", str(CONTRACT_ADAPTER), "--agent-command", str(fake)]
            completed = subprocess.run(command, text=True, capture_output=True, timeout=15, env={**os.environ, "WATCHDOG_RUN_DIR": str(run)})
            self.assertEqual(completed.returncode, 0, completed.stderr)
            manifest = json.loads((workspace / "allowed-inputs.json").read_text())
            result = json.loads((phase / "invocation-result.json").read_text())
            self.assertEqual(result["allowed_input_manifest_hash"], manifest["manifest_hash"])
            self.assert_schema(workspace / "allowed-inputs.json", "allowed-inputs")

    def test_phase_before_gate_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"; marker = run / "called"
            write_json(run / "run-config.json", {
                "initial_state": "PRELIMINARY_REVIEW",
                "phase_runs": [{"agent_id": "reviewer-r1", "role": "reviewer", "phase": "initial-review"}],
            })
            runner(fake, f"import pathlib\npathlib.Path({str(marker)!r}).touch()\n")
            result = self.invoke(run, fake, "--once")
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads((run / "agents/reviewer-r1/phases/initial-review/state.json").read_text())
            self.assertEqual(state["status"], "blocked")
            self.assertEqual(state["failure_category"], "entry_gate")
            self.assertFalse((run / "agents/reviewer-r1/phases/initial-review/state.runtime").exists())
            self.assertEqual((state["attempt"], state["attempt_count"], state["last_artifact_hash"]), (0, 0, None))
            self.assert_schema(run / "agents/reviewer-r1/phases/initial-review/state.json", "phase-state")
            self.assertFalse(marker.exists())

    def test_initialize_migrates_legacy_sidecar_and_zero_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "run_id": "legacy-run", "initial_state": "AUTHOR_REBUTTAL",
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": []}],
            })
            runner(fake, "raise SystemExit(0)\n")
            phase = run / "agents/author/phases/rebuttal"
            write_json(phase / "state.json", {"phase": "rebuttal", "status": "pending", "current_task": None, "attempt": 1, "attempt_count": 1, "last_artifact_hash": "sha256:" + "0" * 64, "no_progress_count": 0})
            write_json(phase / "state.runtime", {"status": "backoff", "attempt": 2, "failure_category": "legacy_crash", "next_eligible_at": "2099-01-01T00:00:00Z", "last_artifact_hash": None})
            args = argparse.Namespace(run_dir=str(run), config=None, runner=str(fake), once=True, poll_seconds=0.02, heartbeat_timeout_seconds=300.0)
            watchdog = Watchdog(args)
            try:
                watchdog.initialize()
                migrated = json.loads((phase / "state.json").read_text())
                self.assertEqual((migrated["status"], migrated["attempt"], migrated["last_artifact_hash"]), ("pending", 2, None))
                self.assertEqual(migrated["failure_category"], "legacy_crash")
                self.assertFalse((phase / "state.runtime").exists())
                self.assert_schema(phase / "state.json", "phase-state")
            finally:
                watchdog.terminate_children()
                shutil.rmtree(run / ".watchdog.lock", ignore_errors=True)

    def test_crash_restarts_same_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_REBUTTAL", "initial_backoff_seconds": 0, "max_backoff_seconds": 0,
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": []}],
            })
            runner(fake, """import hashlib,json,os,pathlib,sys
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); n=p/'calls'; count=int(n.read_text())+1 if n.exists() else 1; n.write_text(str(count))
if count == 1: sys.exit(7)
a=p/'artifacts'/'validated'/'rebuttal.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}'); h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads((run / "agents/author/phases/rebuttal/state.json").read_text())
            self.assertEqual(state["attempt"], 6)
            self.assertEqual(json.loads((run / "agents/author/identity.json").read_text())["agent_id"], "author")

    def test_no_progress_becomes_stalled(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_FINAL", "safety": {"no_progress_threshold": 2},
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "final-followup", "gates": [], "completion_gates": ["never_satisfied"], "requires_artifact": False}],
            })
            runner(fake, "import json,os,pathlib\np=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':False}))\n")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads((run / ".watchdog/status.json").read_text())["status"], "STALLED")

    def test_default_agent_loop_settles_complete_promise(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake-agent.sh"
            executable(fake, "python3 -c 'import sys; sys.stdin.read()'\nprintf '{\"message\":\"hello\"}\\n' > \"$RALPH_OUTPUT_ARTIFACT\"\nprintf '<promise>COMPLETE</promise>\\n'\n")
            write_json(run / "run-config.json", self.agent_loop_config(run, fake))
            result = subprocess.run([str(WATCHDOG), "--run-dir", str(run), "--poll-seconds", "0.02"], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            phase = run / "agents/author/phases/final-followup"
            invocation = json.loads((phase / "invocation-result.json").read_text())
            self.assertEqual((invocation["status"], invocation["promise"]), ("settled", "COMPLETE"))
            self.assertEqual(json.loads((phase / "state.json").read_text())["status"], "completed")
            self.assertEqual(json.loads((run / ".watchdog/status.json").read_text())["status"], "SUCCESS")
            self.assert_schema(phase / "invocation-result.json", "invocation-result")
            self.assertEqual(json.loads((phase / "current-task-context.json").read_text())["attempt"], 4)

    def test_complete_watchdog_run_tree_validates(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / "complete-watchdog-run"; fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "config_version": 1, "run_id": "complete-watchdog-run", "mode": "live_submission",
                "review_start_time": "2026-07-11T00:00:00Z", "literature_cutoff": "2026-01-28T23:59:59-12:00",
                "submission_manifest_path": "submission/submission-manifest.json", "reviewer_count": 3,
            })
            write_json(run / "watchdog-config.json", {
                "schema_version": 1, "run_id": "complete-watchdog-run", "initial_run_state": "PRELIMINARY_REVIEW",
                "phase_runs": [{"agent_id": "reviewer-r1", "role": "reviewer", "phase": "initial-review", "gates": []}],
            })
            runner(fake, """import datetime,hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); a=p/'artifacts'/'validated'/'claim.json'; a.parent.mkdir(parents=True,exist_ok=True)
claim={'claim_id':'claim-1','type':'methodological','statement':'The watchdog completed its bounded work item.','anchor':'runtime','supporting_items':[],'dependencies':[],'scope':'narrow','centrality':'minor'}
a.write_text(json.dumps(claim)); h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest()
result={'schema_version':1,'agent_id':'reviewer-r1','role':'reviewer','phase':'initial-review','status':'settled','promise':'COMPLETE','reason':None,'exit_code':0,'allowed_input_manifest_hash':'sha256:'+'a'*64,'artifact_path':str(a),'artifact_hash':h,'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00','Z')}
(p/'invocation-result.json').write_text(json.dumps(result))
""")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            validation = subprocess.run([str(VALIDATE_RUN), str(run)], text=True, capture_output=True, timeout=30)
            self.assertEqual(validation.returncode, 0, validation.stderr)
            self.assertIn("validated", validation.stdout)
            self.assertFalse(any(run.rglob("state.runtime")))

    def test_agent_loop_validation_reopens_without_crash_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake-agent.sh"
            executable(fake, "count_file=$RALPH_WORKSPACE/count\ncount=0\nif [ -f \"$count_file\" ]; then count=$(python3 -c 'import sys; print(int(open(sys.argv[1]).read()))' \"$count_file\"); fi\ncount=$((count + 1))\nprintf '%s' \"$count\" > \"$count_file\"\nif [ \"$count\" -eq 1 ]; then printf '{}\\n' > \"$RALPH_OUTPUT_ARTIFACT\"; else printf '{\"message\":\"hello\"}\\n' > \"$RALPH_OUTPUT_ARTIFACT\"; fi\nprintf '<promise>COMPLETE</promise>\\n'\n")
            write_json(run / "run-config.json", self.agent_loop_config(run, fake))
            result = subprocess.run([str(WATCHDOG), "--run-dir", str(run), "--poll-seconds", "0.02"], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            phase = run / "agents/author/phases/final-followup"
            self.assertEqual(json.loads((phase / "state.json").read_text())["attempt"], 5)
            budget = json.loads((run / ".watchdog/run-budget.json").read_text())
            self.assertEqual(budget["restart_counts"], {})
            self.assertFalse((phase / "reopen-feedback.txt").exists())

    def test_agent_loop_manifest_violation_is_policy_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake-agent.sh"
            executable(fake, "python3 -c 'import sys; sys.stdin.read()'\nprintf 'read\\t/etc/passwd\\n' > \"$RALPH_ACCESSED_PATHS_LOG\"\nprintf '{\"message\":\"hello\"}\\n' > \"$RALPH_OUTPUT_ARTIFACT\"\nprintf '<promise>COMPLETE</promise>\\n'\n")
            write_json(run / "run-config.json", self.agent_loop_config(run, fake))
            result = subprocess.run([str(WATCHDOG), "--run-dir", str(run), "--poll-seconds", "0.02"], text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            status = json.loads((run / ".watchdog/status.json").read_text())
            self.assertEqual((status["status"], status["run_state"]), ("POLICY_BLOCKED", "POLICY_BLOCKED"))

    def test_role_phase_order_refuses_followup_before_initial(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "PRELIMINARY_REVIEW",
                "phase_runs": [
                    {"agent_id": "reviewer-r1", "role": "reviewer", "phase": "initial-review", "gates": []},
                    {"agent_id": "reviewer-r1", "role": "reviewer", "phase": "followup", "run_states": ["PRELIMINARY_REVIEW"], "gates": []},
                ],
            })
            runner(fake, "import time\ntime.sleep(30)\n")
            result = self.invoke(run, fake, "--once")
            self.assertEqual(result.returncode, 0, result.stderr)
            followup = json.loads((run / "agents/reviewer-r1/phases/followup/state.json").read_text())
            self.assertEqual(followup["status"], "blocked")
            self.assertEqual(followup["failure_category"], "phase_gate")
            self.assertFalse((run / "agents/reviewer-r1/phases/followup/state.runtime").exists())

    def test_run_state_advances_exactly_one_legal_step(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "PRELIMINARY_REVIEW", "auto_advance_run_state": True,
                "phase_runs": [{"agent_id": "reviewer-r1", "role": "reviewer", "phase": "initial-review", "run_states": ["PRELIMINARY_REVIEW"], "gates": []}],
            })
            runner(fake, "raise SystemExit(0)\n")
            args = argparse.Namespace(run_dir=str(run), config=None, runner=str(fake), once=True, poll_seconds=0.02, heartbeat_timeout_seconds=300.0)
            watchdog = Watchdog(args)
            watchdog.initialize()
            try:
                watchdog.state_write(watchdog.phases[0], status="completed")
                watchdog.reconcile()
                status = json.loads((run / ".watchdog/status.json").read_text())
                self.assertEqual((status["status"], status["run_state"]), ("RUNNING", "VALIDATION"))
            finally:
                shutil.rmtree(run / ".watchdog.lock", ignore_errors=True)

    def test_subscription_change_wakes_idle_phase(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"; marker = run / "called"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_FINAL",
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "final-followup", "gates": [], "requires_artifact": False, "subscriptions": [{"path": "published/*.json"}]}],
            })
            runner(fake, f"import pathlib,time\npathlib.Path({str(marker)!r}).touch()\ntime.sleep(30)\n")
            args = argparse.Namespace(run_dir=str(run), config=None, runner=str(fake), once=True, poll_seconds=0.02, heartbeat_timeout_seconds=300.0)
            watchdog = Watchdog(args); watchdog.initialize(); phase = watchdog.phases[0]
            try:
                watchdog.state_write(phase, status="idle")
                watchdog.reconcile()
                self.assertFalse(marker.exists())
                write_json(run / "published/wakeup.json", {"ready": True})
                watchdog.reconcile()
                for _ in range(50):
                    if marker.exists(): break
                    time.sleep(0.01)
                self.assertTrue(marker.exists())
                self.assertIn("subscription_wakeup", (run / "events.ndjson").read_text())
            finally:
                watchdog.terminate_children()
                for child in watchdog.children.values():
                    try: child.wait(timeout=2)
                    except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=2)
                shutil.rmtree(run / ".watchdog.lock", ignore_errors=True)

    def test_discussion_round_ceiling_is_honest(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "INTERNAL_DISCUSSION", "safety": {"max_discussion_rounds": 1, "no_progress_threshold": 5},
                "phase_runs": [{"agent_id": "reviewer-r1", "role": "reviewer", "phase": "discussion", "gates": [], "requires_artifact": False}],
            })
            runner(fake, "import json,os,pathlib\np=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); (p/'invocation-result.json').write_text(json.dumps({'status':'next','validated':False}))\n")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads((run / ".watchdog/status.json").read_text())
            self.assertEqual(status["status"], "INCOMPLETE")
            self.assertIn("discussion_round_ceiling", status["reason"])

    def test_fresh_heartbeat_prevents_false_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_REBUTTAL",
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": []}],
            })
            runner(fake, """import datetime,hashlib,json,os,pathlib,time
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR'])
for _ in range(30):
    (p/'heartbeat').write_text(datetime.datetime.now(datetime.timezone.utc).isoformat())
    time.sleep(0.05)
a=p/'artifacts'/'validated'/'rebuttal.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}')
h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            result = self.invoke(run, fake, "--heartbeat-timeout-seconds", "1")
            self.assertEqual(result.returncode, 0, result.stderr)
            budget = json.loads((run / ".watchdog/run-budget.json").read_text())
            self.assertEqual(budget["restart_counts"], {})

    def test_term_forwards_and_resume_keeps_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_REBUTTAL", "initial_backoff_seconds": 0, "max_backoff_seconds": 0,
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "rebuttal", "gates": []}],
            })
            runner(fake, "import time\ntime.sleep(30)\n")
            process = subprocess.Popen([str(WATCHDOG), "--run-dir", str(run), "--runner", str(fake), "--poll-seconds", "0.02"])
            state_path = run / "agents/author/phases/rebuttal/state.json"
            for _ in range(100):
                if state_path.exists() and json.loads(state_path.read_text()).get("status") == "running":
                    break
                time.sleep(0.02)
            process.terminate()
            self.assertEqual(process.wait(timeout=5), 0)
            self.assertEqual(json.loads((run / ".watchdog/status.json").read_text())["status"], "INCOMPLETE")
            identity = json.loads((run / "agents/author/identity.json").read_text())
            runner(fake, """import hashlib,json,os,pathlib
p=pathlib.Path(os.environ['WATCHDOG_PHASE_DIR']); a=p/'artifacts'/'validated'/'rebuttal.json'; a.parent.mkdir(parents=True,exist_ok=True); a.write_text('{}'); h='sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(); (p/'invocation-result.json').write_text(json.dumps({'status':'complete','validated':True,'artifact_hash':h}))
""")
            resumed = self.invoke(run, fake)
            self.assertEqual(resumed.returncode, 0, resumed.stderr)
            self.assertEqual(json.loads((run / ".watchdog/status.json").read_text())["status"], "SUCCESS")
            self.assertEqual(json.loads((run / "agents/author/identity.json").read_text()), identity)

    def test_wall_clock_exhaustion_is_honest(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp); fake = run / "fake.py"
            write_json(run / "run-config.json", {
                "initial_state": "AUTHOR_FINAL", "safety": {"max_wall_clock_hours": 0},
                "phase_runs": [{"agent_id": "author", "role": "author", "phase": "final-followup", "gates": []}],
            })
            runner(fake, "raise SystemExit(0)\n")
            result = self.invoke(run, fake)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads((run / ".watchdog/status.json").read_text())["status"], "TIME_EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
