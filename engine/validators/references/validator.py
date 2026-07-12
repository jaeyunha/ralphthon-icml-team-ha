"""Reference identity, support, publication-status, and challenge recheck logic."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any

from engine.validators.arbitration.contracts import validate_finding

YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
ARXIV_RE = re.compile(r"arXiv\s*:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?)", re.I)
DOI_RE = re.compile(r"(?:doi\s*:\s*|https?://doi\.org/)(10\.\d{4,9}/\S+)", re.I)
TOKEN_RE = re.compile(r"[a-z0-9]+")
TITLE_END_RE = re.compile(
    r"[.?]\s+(?:In\b|arXiv:|Data in Brief|Mendeley Data|Neural Networks|IEEE|"
    r"PhD thesis|Accepted for publication|Proceedings)"
)


def extract_reference_metadata(reference: dict[str, Any]) -> dict[str, Any]:
    """Extract conservative lookup metadata from one dossier reference entry."""

    statement = str(reference.get("statement", "")).strip()
    year = YEAR_RE.search(statement)
    arxiv = ARXIV_RE.search(statement)
    doi = DOI_RE.search(statement)
    title = _reference_title(statement)
    return {
        "reference_id": str(reference.get("id", "unknown-reference")),
        "anchor": str(reference.get("anchor_id", "")),
        "query": " ".join(item for item in (title, year.group(0) if year else "") if item),
        "title": title,
        "authors_text": "",
        "year": int(year.group(0)) if year else None,
        "arxiv_id": arxiv.group(1) if arxiv else None,
        "doi": doi.group(1).rstrip(".,") if doi else None,
        "statement": statement,
    }


def build_broker_requests(
    dossier: dict[str, Any],
    target_fingerprint: dict[str, Any],
    *,
    run_id: str,
    reviewer_id: str,
    literature_cutoff: str,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    """Create one cutoff-aware broker request for each bibliography entry."""

    timestamp = created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z")
    references = dossier.get("references", [])
    if not isinstance(references, list):
        raise ValueError("dossier references must be a list")
    requests: list[dict[str, Any]] = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        metadata = extract_reference_metadata(reference)
        reference_id = metadata["reference_id"]
        requests.append(
            {
                "requestId": f"REF-{hashlib.sha256(reference_id.encode()).hexdigest()[:16]}",
                "runId": run_id,
                "reviewerId": reviewer_id,
                "query": metadata["query"],
                "queryKind": "cited_work_lookup",
                "retrievalReason": f"Validate bibliography identity for {reference_id}",
                "mode": "historical_benchmark",
                "literatureCutoff": literature_cutoff,
                "targetFingerprint": target_fingerprint,
                "maxResults": 3,
                "createdAt": timestamp,
            }
        )
    return requests


def validate_references(
    dossier: dict[str, Any],
    broker_results: dict[str, dict[str, Any]],
    *,
    citation_claims: list[dict[str, Any]] | None = None,
    publication_statuses: dict[str, str] | None = None,
    challenged_finding_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Validate bibliography identities and citation support from broker evidence."""

    references = dossier.get("references", [])
    if not isinstance(references, list):
        raise ValueError("dossier references must be a list")
    challenged = challenged_finding_ids or set()
    statuses = publication_statuses or {}
    findings: list[dict[str, Any]] = []
    identity_by_reference: dict[str, str] = {}

    for reference in references:
        if not isinstance(reference, dict):
            continue
        metadata = extract_reference_metadata(reference)
        reference_id = metadata["reference_id"]
        result = broker_results.get(reference_id)
        finding = _identity_finding(metadata, result, challenged)
        findings.append(finding)
        identity_by_reference[reference_id] = finding["status"]
        publication = statuses.get(reference_id)
        if publication:
            findings.append(_publication_finding(metadata, publication))

    for index, claim in enumerate(citation_claims or [], start=1):
        findings.append(_support_finding(index, claim, challenged))

    return {
        "validator": "references",
        "findings": findings,
        "identity_statuses": identity_by_reference,
        "challenge_policy": "challenged findings are recomputed from broker evidence and never defended by default",
    }


def _identity_finding(
    metadata: dict[str, Any],
    result: dict[str, Any] | None,
    challenged: set[str],
) -> dict[str, Any]:
    reference_id = metadata["reference_id"]
    finding_id = f"REF-ID-{reference_id}"
    method_prefix = "Rechecked after author challenge. " if finding_id in challenged else ""
    if result is None:
        return _finding(
            finding_id,
            "reference_identity",
            reference_id,
            "unresolved",
            "minor",
            [metadata["anchor"]],
            method_prefix + "No broker response was available for identity verification.",
            "Reference identity remains unresolved because the required broker result is missing.",
            "No network inference or local guess was substituted for broker evidence.",
            ["broker-response presence audit"],
            0.99,
        )
    if result.get("artifact_type") == "literature_broker_refusal":
        code = str(result.get("code", "UNKNOWN"))
        details = result.get("details")
        absence_confirmed = (
            isinstance(details, dict)
            and details.get("absence_confirmed") is True
            and isinstance(details.get("independent_registry_checks"), list)
            and len(set(map(str, details["independent_registry_checks"]))) >= 2
        )
        no_source = code == "NO_ADMISSIBLE_SOURCES" and result.get("stage") in {
            "source_discovery",
            "full_text_retrieval",
        }
        status = (
            "confirmed_nonexistent"
            if absence_confirmed
            else ("likely_nonexistent" if no_source else "unresolved")
        )
        severity = "major" if absence_confirmed else "minor"
        return _finding(
            finding_id,
            "reference_identity",
            reference_id,
            status,
            severity,
            [metadata["anchor"]],
            method_prefix
            + "Queried the controlled literature broker and inspected its typed refusal and rejection provenance.",
            (
                "Independent canonical registries confirmed that no matching scholarly source exists."
                if absence_confirmed
                else (
                    "No admissible source was retrieved; the identity is likely nonexistent but not independently confirmed."
                    if no_source
                    else f"Broker refused or could not complete the lookup ({code})."
                )
            ),
            "A broker refusal alone is never treated as confirmed nonexistence.",
            (
                ["broker multi-backend lookup", "independent canonical-registry absence check"]
                if absence_confirmed
                else ["typed broker refusal audit"]
            ),
            0.99 if absence_confirmed else (0.72 if no_source else 0.9),
        )

    packets = result.get("packets", [])
    if not isinstance(packets, list) or not packets:
        return _identity_finding(metadata, None, challenged)
    usable_packets = [packet for packet in packets if isinstance(packet, dict)]
    if not usable_packets:
        return _identity_finding(metadata, None, challenged)
    packet = max(
        usable_packets,
        key=lambda item: _title_coverage(metadata["statement"], str(item.get("title", ""))),
    )
    title_similarity = _title_coverage(metadata["statement"], str(packet.get("title", "")))

    cited_year = metadata.get("year")
    source_year = _year(packet.get("first_public_date"))
    year_matches = cited_year is None or source_year is None or cited_year == source_year
    if title_similarity >= 0.8 and year_matches:
        status, severity = "verified_exact", "none"
    elif title_similarity >= 0.8:
        status, severity = "metadata_mismatch", "major"
    elif title_similarity >= 0.65:
        status, severity = "verified_with_minor_metadata_difference", "minor"
    else:
        status, severity = "unresolved", "minor"
    confirmations = ["broker source-identity verification"]
    if severity == "major":
        confirmations.append("independent title/year metadata comparison")
    return _finding(
        finding_id,
        "reference_identity",
        reference_id,
        status,
        severity,
        [metadata["anchor"]],
        method_prefix
        + "Compared the cited title and year with the broker's canonical, retrieved, content-hashed source identity.",
        f"Title token similarity={title_similarity:.2f}; cited year={cited_year}; source year={source_year}.",
        "Author-name normalization is conservative and typographic extraction noise may lower similarity.",
        confirmations,
        min(0.99, 0.75 + 0.24 * title_similarity),
        [str(packet.get("canonical_uri", "")), str(packet.get("content_hash", ""))],
    )


def _support_finding(index: int, claim: dict[str, Any], challenged: set[str]) -> dict[str, Any]:
    finding_id = str(claim.get("finding_id", f"REF-SUPPORT-{index:03d}"))
    source_text = str(claim.get("source_text", ""))
    attached_claim = str(claim.get("attached_claim", ""))
    explicit = claim.get("support_status")
    similarity = _token_similarity(attached_claim, source_text)
    if isinstance(explicit, str):
        status = explicit
    elif not source_text.strip():
        status = "source_inaccessible"
    elif similarity < 0.12:
        status = "source_never_makes_claim"
    elif similarity < 0.3:
        status = "does_not_support"
    elif similarity < 0.55:
        status = "partially_supports"
    else:
        status = "directly_supports"
    severity = (
        "major"
        if status in {"contradicts", "source_never_makes_claim"}
        else ("minor" if status in {"does_not_support", "partially_supports"} else "none")
    )
    confirmations = ["full-text claim/passage comparison"]
    if severity == "major":
        confirmations.append("independent passage search for claim predicates")
    method = "Compared the attached paper claim with the broker-retrieved source text."
    if finding_id in challenged:
        method = "Rechecked the broker evidence after an author challenge; " + method.casefold()
    return _finding(
        finding_id,
        "citation_support",
        str(claim.get("claim_id")) if claim.get("claim_id") else None,
        status,
        severity,
        [str(claim.get("anchor", ""))],
        method,
        f"Claim/source token similarity={similarity:.2f}. {claim.get('observation', '')}".strip(),
        "Token overlap is only a deterministic screening aid; semantic adjudication requires the recorded full-text passages.",
        confirmations,
        0.96 if status == "source_never_makes_claim" else 0.82,
        [str(item) for item in claim.get("artifact_refs", []) if isinstance(item, str)],
    )


def _publication_finding(metadata: dict[str, Any], status: str) -> dict[str, Any]:
    allowed = {
        "current",
        "corrected",
        "retracted",
        "withdrawn",
        "superseded",
        "expression_of_concern",
        "version_mismatch",
        "unknown",
    }
    normalized = status if status in allowed else "unknown"
    severity = (
        "major"
        if normalized in {"retracted", "withdrawn"}
        else (
            "minor"
            if normalized
            in {"corrected", "superseded", "expression_of_concern", "version_mismatch"}
            else "none"
        )
    )
    paths = ["publication-status registry check"]
    if severity == "major":
        paths.append("publisher notice confirmation")
    return _finding(
        f"REF-PUB-{metadata['reference_id']}",
        "publication_status",
        metadata["reference_id"],
        normalized,
        severity,
        [metadata["anchor"]],
        "Checked the broker-linked canonical record for correction, retraction, withdrawal, and version notices.",
        f"Publication status: {normalized}.",
        "Some notices propagate slowly across registries.",
        paths,
        0.95 if normalized != "unknown" else 0.5,
    )


def _finding(
    finding_id: str,
    validator_type: str,
    claim_id: str | None,
    status: str,
    severity: str,
    anchors: list[str],
    method: str,
    observation: str,
    limitations: str,
    confirmation_paths: list[str],
    confidence: float,
    artifact_refs: list[str] | None = None,
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "finding_id": finding_id,
        "validator_type": validator_type,
        "claim_id": claim_id,
        "status": status,
        "severity_candidate": severity,
        "paper_anchors": sorted(set(anchor for anchor in anchors if anchor)),
        "method": method,
        "observation": observation,
        "limitations": limitations,
        "confirmation_paths": confirmation_paths,
        "confidence": confidence,
    }
    refs = sorted(set(ref for ref in artifact_refs or [] if ref))
    if refs:
        finding["artifact_refs"] = refs
    return validate_finding(finding)


def _token_similarity(left: str, right: str) -> float:
    left_tokens = set(TOKEN_RE.findall(left.casefold()))
    right_tokens = set(TOKEN_RE.findall(right.casefold()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _title_coverage(citation: str, candidate_title: str) -> float:
    stopwords = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}
    citation_tokens = {
        token
        for token in TOKEN_RE.findall(citation.casefold())
        if len(token) > 1 and token not in stopwords
    }
    title_tokens = {
        token
        for token in TOKEN_RE.findall(candidate_title.casefold())
        if len(token) > 1 and token not in stopwords
    }
    if not title_tokens:
        return 0.0
    return len(citation_tokens & title_tokens) / len(title_tokens)


def _reference_title(statement: str) -> str:
    venue = TITLE_END_RE.search(statement)
    prefix = statement[: venue.start()] if venue else statement.rsplit(".", 1)[0]
    return prefix.rsplit(". ", 1)[-1].strip(" .") or statement


def _year(value: object) -> int | None:
    match = YEAR_RE.search(str(value))
    return int(match.group(0)) if match else None
