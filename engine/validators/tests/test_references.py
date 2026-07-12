from __future__ import annotations

import json
from pathlib import Path


from engine.validators.references import build_broker_requests, validate_references

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "validators-statref"


def load(name: str) -> object:
    return json.loads((FIXTURE / name).read_text(encoding="utf-8"))


def test_fake_reference_and_misquoted_source_are_caught() -> None:
    report = validate_references(
        load("planted-references-dossier.json"),
        load("planted-broker-results.json"),
        citation_claims=load("planted-citation-claims.json"),
    )
    findings = {finding["finding_id"]: finding for finding in report["findings"]}

    assert findings["REF-ID-REF-FAKE"]["status"] == "confirmed_nonexistent"
    assert len(findings["REF-ID-REF-FAKE"]["confirmation_paths"]) == 2
    assert findings["REF-SUPPORT-PLANTED"]["status"] == "source_never_makes_claim"
    assert len(findings["REF-SUPPORT-PLANTED"]["confirmation_paths"]) == 2


def test_challenge_path_rechecks_instead_of_defending_prior_result() -> None:
    report = validate_references(
        load("planted-references-dossier.json"),
        load("planted-broker-results.json"),
        citation_claims=load("planted-citation-claims.json"),
        challenged_finding_ids={"REF-SUPPORT-PLANTED"},
    )
    finding = next(
        item for item in report["findings"] if item["finding_id"] == "REF-SUPPORT-PLANTED"
    )
    assert "Rechecked" in finding["method"]


def test_broker_requests_match_broker_contract() -> None:
    dossier = load("planted-references-dossier.json")
    request_fixture = json.loads(
        (ROOT / "tests" / "fixtures" / "broker" / "query-request.json").read_text(encoding="utf-8")
    )
    requests = build_broker_requests(
        dossier,
        request_fixture["targetFingerprint"],
        run_id="run-reference-test",
        reviewer_id="validator-references",
        literature_cutoff="2026-01-28T23:59:59-12:00",
        created_at="2026-01-28T12:00:00Z",
    )
    required = {
        "requestId",
        "runId",
        "reviewerId",
        "query",
        "queryKind",
        "retrievalReason",
        "mode",
        "literatureCutoff",
        "targetFingerprint",
        "maxResults",
        "createdAt",
    }
    assert len(requests) == 2
    assert all(set(request) == required for request in requests)
    assert all(request["queryKind"] == "cited_work_lookup" for request in requests)
