// Generated from JSON Schema. Do not edit by hand.
// Run `bun run generate:types` from packages/schemas.

export type AllowedInputs = {
  "agent_id": string;
  "inputs": Array<{
    "category": "own_private_state" | "paper" | "validation" | "other_reviews" | "author_response" | "internal_discussion" | "policy" | "rubric" | "role_prompt" | "phase_prompt" | "persona" | "task_context" | "schema";
    "path": string;
    "visibility": "full" | "published_only" | "own_thread" | "author_visible" | "followups" | "prior_responses" | "ac_issues" | "final_record" | "as_needed";
  }>;
  "manifest_hash": string;
  "permissions": {
    "author_response": "no" | "own-thread" | "yes" | "not-applicable" | "prior-responses" | "published";
    "internal_discussion": "no" | "ac-issues" | "yes" | "no-private-prep" | "full" | "full-record" | "final-record";
    "other_reviews": "no" | "no-by-default" | "yes" | "all-official-reviews" | "followups";
    "own_private_state": "yes";
    "paper": "yes" | "as-needed";
    "validation": "published-bundle-only" | "yes" | "author-visible";
  };
  "phase": string;
  "role": "reviewer" | "author" | "ac" | "sac" | "pc" | "validator_code" | "validator_mathematics" | "validator_statistics" | "validator_references" | "validator_ethics" | "validator_arbitration";
  "run_id": string;
  "schema_version": 1;
};

export type Anchors = {
  "anchors": {
    [key: string]: {
      "anchor_id": string;
      "asset_paths": Array<string>;
      "bbox": Array<number>;
      "confidence": number;
      "content_sha256": string;
      "page": number;
      "source_ref": string;
      "type": "section" | "figure" | "table" | "equation" | "theorem" | "citation" | "text";
    };
  };
  "schema_version": "1.0";
};

export type BenchmarkArmDecisionBundle = {
  "arm_cohort_id": string;
  "bundle_hash": string;
  "campaign_id": string;
  "decisions": Array<BenchmarkPcDecision>;
  "finalized_at": string;
  "paper_ledger_hashes": Array<string>;
  "pc_id": string;
  "reconciliation_roots": {
    "custody": string;
    "metering": string;
    "provenance": string;
  };
  "runtime_evidence_roots": {
    "broker_snapshot_hash": string;
    "runtime_packet_ledger_root": string;
  };
  "sac_action_history_ref": string;
  "sac_bundle_hash": string;
  "status": "finalized" | "failed";
  "version": 1;
};

export type BenchmarkArmFreeze = {
  "arm_bundle_hash": string;
  "arm_bundle_ref": string;
  "arm_cohort_id": string;
  "campaign_id": string;
  "custody_root": string;
  "decision_hashes": Array<string>;
  "freeze_hash": string;
  "frozen_at": string;
  "metering_root": string;
  "paper_ledger_hashes": Array<string>;
  "provenance_root": string;
  "status": "terminal" | "failed";
  "version": 1;
};

export type BenchmarkArtifactProvenance = {
  "cutoff": "2026-01-28T23:59:59-12:00";
  "first_public_at": string;
  "kind": "original_pdf" | "supplement" | "attachment" | "code_archive" | "repository_commit" | "repository_tree" | "data" | "checkpoint" | "ever_packet" | "human_thread";
  "revision": string | null;
  "sha256": string;
  "size_bytes": number;
  "source_uri": string;
  "status": "eligible" | "ineligible" | "current_snapshot_only" | "missing";
};

export type BenchmarkBrokerSnapshot = {
  "config_hash": string;
  "cutoff": "2026-01-28T23:59:59-12:00";
  "implementation_hash": string;
  "index_hash": string;
  "manifest_hash": string;
};

export type BenchmarkCustodyState = {
  "campaign_id": string;
  "history": Array<"planned" | "provenance_locked" | "profiles_locked" | "running" | "arms_terminal" | "generated_annotations_frozen" | "reveal_ready" | "revealed" | "scored" | "quarantined">;
  "prerequisites": null | {
    "adjudication_hash": string;
    "arm_freeze_hashes": Array<string>;
    "campaign_manifest_hash": string;
    "generated_annotations_hash": string;
    "gold_annotations_hash": string;
    "job_reconciliation_hash": string;
    "prerequisite_hash": string;
    "reliability_hash": string;
    "scorer_hash": string;
    "usage_reconciliation_hash": string;
  };
  "quarantine_reason": string | null;
  "reveal_count": number;
  "state": "planned" | "provenance_locked" | "profiles_locked" | "running" | "arms_terminal" | "generated_annotations_frozen" | "reveal_ready" | "revealed" | "scored" | "quarantined";
  "state_hash": string;
  "version": 1;
};

export type BenchmarkEvidencePacket = {
  "content_sha256": string;
  "cutoff": "2026-01-28T23:59:59-12:00";
  "packet_hash": string;
  "query_fingerprint": string;
  "response_sha256": string;
  "response_size_bytes": number;
  "retrieved_at": string;
  "sanitized_response": string;
  "source_uri": string;
};

export type BenchmarkJobEvent = {
  "assignment": string;
  "closed_at_ns": number | null;
  "event_hash": string;
  "job_id": string;
  "kind": "start" | "heartbeat" | "stop" | "expired";
  "monotonic_ns": number;
  "previous_event_hash": string | null;
  "sequence": number;
};

export type BenchmarkMeteringReconciliation = {
  "cap_status": "within_caps";
  "job_interval_hashes": Array<string>;
  "job_reconciliation_hash": string;
  "ledger_totals": Array<{
    "assignment": string;
    "job_hours": string;
    "tokens": number;
    "usd": string;
  }>;
  "provider_reconciliation_hash": string;
  "provider_record_hashes": Array<string>;
  "reconciliation_hash": string;
  "total_job_hours": string;
  "total_tokens": number;
  "total_usd": string;
};

export type BenchmarkPcDecision = {
  "arm_cohort_id": string;
  "campaign_id": string;
  "decision_hash": string;
  "evidence_refs": Array<string>;
  "finalized_at": string;
  "meta_review_ref": string | null;
  "outcome": "accept" | "reject" | "failed";
  "paper_id": string;
  "paper_slot": number;
  "pc_id": string;
  "reason": string;
  "sac_ref": string;
  "terminal_failure_code": string | null;
  "unresolved_dissent": Array<string>;
  "version": 1;
};

export type BenchmarkProviderUsage = {
  "assignment": string;
  "billed_usd": string;
  "cached_input_tokens": number;
  "input_tokens": number;
  "invocation_id": string;
  "output_tokens": number;
  "provider": string;
  "provider_record_hash": string;
  "record_hash": string;
  "runtime_settings_hash": string;
};

export type BenchmarkReplacementLedger = {
  "allocation_hash": string;
  "allocations": Array<{
    "consume_order": number;
    "intended_forum_id": string;
    "replacement_forum_id": string;
    "replacement_sort_hash": string;
    "slot_id": string;
    "stratum": string;
  }>;
  "campaign_id": string;
  "exhausted_slots": Array<string>;
  "source_universe_hash": string;
  "version": 1;
};

export type BenchmarkRuntimeSettings = {
  "caps": {
    "arm_job_hours": "2";
    "arm_tokens": 200000;
    "arm_usd": "10";
    "campaign_job_hours": "144";
    "campaign_tokens": 28400000;
    "campaign_usd": "1070";
    "campaign_wall_hours": "72";
    "paper_job_hours": "10";
    "paper_tokens": 2000000;
    "paper_usd": "75";
  };
  "concurrency": 2;
  "context_settings": Record<string, unknown>;
  "heartbeat_interval_seconds": number;
  "invocation_deadline_seconds": number;
  "invocation_retries": 1;
  "lease_timeout_seconds": number;
  "model_snapshot": {
    "attestation_hash": string;
    "attested_at": string;
    "model_identifier": string;
    "provider": string;
    "snapshot_identifier": string;
  };
  "model_snapshot_hash": string;
  "no_progress_limit": 2;
  "phase_deadline_seconds": number;
  "phase_retries": 1;
  "provider_usage_mapping": {
    "cached_input_tokens_field": string | null;
    "input_tokens_field": string;
    "output_tokens_field": string;
  };
  "queue_semantics": string;
  "rate_card_hash": string;
  "reasoning_settings": Record<string, unknown>;
  "settings_hash": string;
  "tool_settings": Record<string, unknown>;
  "version": 1;
};

export type BenchmarkSacCalibrationBundle = {
  "arm_cohort_id": string;
  "campaign_id": string;
  "completed_at": string;
  "sac_id": string;
  "slots": Array<{
    "ac_recommendation": "accept" | "reject";
    "action": "affirm" | "request_meta_review_revision";
    "action_history": Array<{
      "action": "affirm" | "request_meta_review_revision";
      "defects": Array<string>;
      "reason": string;
      "sequence": number;
    }>;
    "evidence_refs": Array<string>;
    "meta_review_hash": string;
    "meta_review_ref": string;
    "paper_id": string;
    "paper_slot": number;
    "recommended_decision": "accept" | "reject";
    "sac_rationale": string;
    "status": "calibrated";
  } | {
    "failure": {
      "code": string;
      "evidence_refs": Array<string>;
      "message": string;
      "occurred_at": string;
      "stage": string;
    };
    "paper_id": string;
    "paper_slot": number;
    "status": "failed";
  }>;
  "status": "calibrated" | "failed";
  "terminal_failure_code"?: string;
  "version": 1;
};

export type BenchmarkSourceUniverse = {
  "candidates": Array<{
    "artifacts": Array<BenchmarkArtifactProvenance>;
    "eligibility_reason": string;
    "eligible": boolean;
    "forum_id": string;
    "original_pdf": BenchmarkArtifactProvenance;
    "stratum": string;
    "submission_number": number;
  }>;
  "cutoff": "2026-01-28T23:59:59-12:00";
  "intended_slots": Array<{
    "forum_id": string;
    "slot_id": string;
    "stratum": string;
    "submission_number": number;
  }>;
  "manifest_hash": string;
  "version": 1;
};

export type BenchmarkSterileRootCapability = {
  "contract_hash": string;
  "denied_capabilities": Array<"repository" | "home" | ".gjc" | "outcome" | "human_thread" | "scorer" | "other_arm" | "dns" | "network" | "package_install" | "git" | "socket" | "credential">;
  "dns_enabled": false;
  "ever_rpc_socket": string;
  "forbidden_roots": Array<string>;
  "network_enabled": false;
  "principal": {
    "arm_id": string | null;
    "campaign_id": string;
    "kind": "custodian" | "matrix_coordinator" | "model_role" | "gold_annotator" | "generated_annotator" | "adjudicator" | "scorer";
    "model_capable": boolean;
    "principal_id": string;
  };
  "prompt_rpc_socket": string;
  "read_only_mounts": Array<string>;
  "role_root": string;
  "version": 1;
};

export type CalibrationFollowupV2 = {
  "concern_resolutions": Array<{
    "assessment": string;
    "concern_id": string;
    "new_question_id"?: string;
    "no_new_question_reason"?: string;
    "paper_evidence"?: Array<string>;
    "remaining_gap": string;
    "response_evidence": Array<string>;
    "score_effect": string;
    "status": "resolved" | "partially_resolved" | "unresolved" | "invalidated_by_response";
  }>;
  "confidence": number;
  "evidence_refs": Array<string>;
  "new_questions": Array<{
    "answer_induced_by": Array<string>;
    "concern_id": string;
    "decision_relevance": string;
    "id": string;
    "question": string;
  }>;
  "official_review_version": number;
  "profile_id": "v2";
  "rebuttal_version": number;
  "reviewer_id": string;
  "score_change_rationale": string;
  "scores": {
    "originality": number;
    "overall": number;
    "presentation": number;
    "significance": number;
    "soundness": number;
  };
  "summary": string;
  "version": 2;
};

export type CalibrationOfficialReviewV2 = {
  "confidence": number;
  "ethical_concerns": Array<string>;
  "evidence_refs": Array<string>;
  "key_questions": Array<{
    "id": string;
    "possible_score_impact": string;
    "question": string;
  }>;
  "limitations": string;
  "overall_judgment": {
    "acceptance_case": {
      "anchors": Array<string>;
      "text": string;
    };
    "dominance_rationale": string;
    "dominant_case": "acceptance" | "rejection";
    "rejection_case": {
      "anchors": Array<string>;
      "text": string;
    };
    "significance_basis": {
      "anchors": Array<string>;
      "text": string;
    };
  };
  "profile_id": "v2";
  "reviewer_id": string;
  "scores": {
    "originality": number;
    "overall": number;
    "presentation": number;
    "significance": number;
    "soundness": number;
  };
  "strengths": Array<{
    "anchors": Array<string>;
    "text": string;
  }>;
  "summary": string;
  "version": 2;
  "weaknesses": Array<{
    "affected_claims": Array<string>;
    "anchors": Array<string>;
    "id": string;
    "severity": "minor" | "major" | "critical";
    "text": string;
  }>;
};

export type Claim = {
  "anchor": string;
  "centrality": "minor" | "major" | "central";
  "claim_id": string;
  "dependencies": Array<string>;
  "scope": "narrow" | "moderate" | "broad";
  "statement": string;
  "supporting_items": Array<string>;
  "type": "theoretical" | "empirical_result" | "empirical_generalization" | "methodological" | "complexity" | "reproducibility" | "novelty" | "other";
};

export type ConcernLedger = {
  "concerns": Array<{
    "affected_claims": Array<string>;
    "anchors": Array<string>;
    "evidence_refs"?: Array<string>;
    "id": string;
    "severity": "minor" | "major" | "critical";
    "status": "open" | "resolved" | "partially_resolved" | "unresolved" | "invalidated_by_response";
    "text": string;
  }>;
  "ledger_version": number;
  "official_review_version": 1;
  "reviewer_id": string;
};

export type ConcernResolution = {
  "concern_id": string;
  "remaining_gap": string | null;
  "resolution": "resolved" | "partially_resolved" | "unresolved" | "invalidated_by_response";
  "response_evidence": Array<string>;
  "score_effect": {
    [key: string]: string;
  };
};

export type Decision = {
  "ac_recommendation": "accept" | "reject";
  "batch"?: {
    "accepted_count": number;
    "rank": number;
    "spotlight_selected": boolean;
  };
  "evidence_refs": Array<string>;
  "final_decision": "accept" | "reject" | "accept_regular" | "accept_spotlight";
  "mode": "single_paper" | "batch";
  "pc_rationale": string;
  "sac_action": "confirmed" | "returned_for_discussion" | "emergency_review_required" | "overridden";
  "spotlight_candidate"?: boolean;
  "submission_id"?: string;
  "unresolved_dissent": Array<string>;
  "version"?: 1;
};

export type DiscussionIssue = {
  "ac_question": string;
  "decisive": boolean;
  "expected_respondents": Array<string>;
  "issue_id": string;
  "positions": Array<Record<string, unknown>>;
  "resolution": string | null;
  "status": "open" | "closed" | "irreducibly_disputed";
  "topic": string;
};

export type DiscussionPosition = {
  "evidence_refs": Array<string>;
  "issue_id": string;
  "position": string;
  "position_id": string;
  "published_at": string;
  "reviewer_id": string;
  "round": number;
  "score_effect": "unchanged" | "raised" | "lowered" | "pending";
};

export type EventDurableTipV2 = {
  "end_offset": number;
  "last_event_hash": string;
  "last_sequence": number;
  "log_dev": number;
  "log_ino": number;
  "schema_version": 2;
};

export type EventEnvelopeV2 = {
  "actor": {
    "agent_id": string;
    "phase": string;
    "role": string;
  };
  "artifact_id"?: string;
  "causation_event_id"?: string;
  "event_hash": string;
  "event_id": string;
  "idempotency_key": string;
  "occurred_at": string;
  "payload": Record<string, unknown>;
  "previous_event_hash": string;
  "run_id": string;
  "schema_version": 2;
  "sequence": number;
  "type": string;
};

export type EventEnvelope = {
  "actor": {
    "agent_id": string;
    "phase": string;
    "role": string;
  };
  "artifact_id"?: string;
  "causation_event_id"?: string;
  "event_id": string;
  "occurred_at": string;
  "payload": Record<string, unknown>;
  "run_id": string;
  "sequence": number;
  "type": string;
};

export type EventSemanticDraftV2 = {
  "actor": {
    "agent_id": string;
    "phase": string;
    "role": string;
  };
  "artifact_id"?: string;
  "causation_event_id"?: string;
  "event_id": string;
  "idempotency_key": string;
  "occurred_at": string;
  "payload": Record<string, unknown>;
  "run_id": string;
  "schema_version": 2;
  "type": string;
};

export type EvidencePacket = {
  "admissibility": "admissible_prior_work" | "admissible_background" | "inadmissible_post_cutoff" | "quarantined_target_duplicate" | "unverified";
  "authors": Array<string>;
  "canonical_uri": string;
  "content_hash": string;
  "first_public_date": string;
  "retrieval_reason": string;
  "source_id": string;
  "source_type": "official_proceedings" | "publisher_page" | "journal" | "pmlr" | "arxiv_preprint" | "acl_anthology" | "cvf_open_access" | "metadata_registry" | "benchmark_documentation" | "official_repository";
  "supporting_passages": Array<{
    "anchor": string;
    "summary": string;
  }>;
  "title": string;
  "verification_status": "metadata_only" | "abstract_checked" | "full_text_checked" | "source_inaccessible";
};

export type ExtractionFixtureContract = {
  "expected_artifacts": Array<{
    "kind": string;
    "path": string;
    "present": boolean;
    "required_for_golden": boolean;
  }>;
  "fixture_id": string;
  "generated_artifacts_present": boolean;
  "paper_id": string;
  "promotion_requirements": {
    "all_expected_artifacts_present": boolean;
    "all_required_invariants_validated": boolean;
    "manual_placeholder_content_forbidden": boolean;
    "real_production_run": boolean;
    "state_after_promotion": "golden";
  };
  "required_invariants": Array<string>;
  "schema_version": 1;
  "source": {
    "note": string;
    "pdf_available_in_checkout": boolean;
    "pdf_committed": boolean;
    "sha256": string;
  };
  "state": "candidate" | "golden";
};

export type ExtractionFixtureManifest = {
  "artifacts": Array<{
    "path": string;
    "sha256": string;
    "size_bytes": number;
  }>;
  "assets": {
    "file_count": number;
    "total_size_bytes": number;
    "tree_sha256": string;
  };
  "dossier_summary": {
    "assumptions": number;
    "claims": number;
    "equations": number;
    "experiments": number;
    "references": number;
    "theorems": number;
  };
  "fixture_id": string;
  "paper_id": string;
  "schema_version": 1;
  "source": {
    "pdf_committed": boolean;
    "pdf_filename": string;
    "pdf_sha256": string;
    "size_bytes": number;
  };
  "state": "candidate" | "golden";
  "tool": {
    "name": "docling";
    "version": string;
  };
  "verification": {
    "sample_size": number;
    "status": "passed" | "failed";
    "unresolved_anchor_count": number;
  };
  "verified_bundle_sha256": string;
};

export type ExtractionReport = {
  "assets": Array<{
    "anchor_id": string;
    "paths": Array<string>;
    "type": "figure" | "table" | "equation";
  }>;
  "extractor": {
    "name": "docling";
    "version": string;
  };
  "parse_verification": {
    "checks": Array<unknown>;
    "status": "pending";
  } | {
    "report_path": "parse-verification-report.json";
    "status": "passed" | "failed";
    "unresolved_anchor_count": number;
  };
  "schema_version": "1.0";
  "source": {
    "pdf_path": string | null;
    "pdf_sha256": string | null;
  };
  "summary": {
    "anchor_count": number;
    "asset_count": number;
    "mean_confidence": number;
    "minimum_confidence": number;
  };
  "suspicious_instruction_evidence": Array<{
    "anchor_id": string;
    "category": "ignore_instructions" | "system_prompt" | "role_override" | "command_execution" | "review_override" | "instruction_delimiter";
    "evidence_excerpt": string;
    "matched_text": string;
    "page": number;
  }>;
  "uncertain_regions": Array<{
    "anchor_id": string;
    "confidence": number;
    "page": number;
    "reason": "docling_confidence_below_threshold";
  }>;
};

export type FinalReview = {
  "confidence": number;
  "discussion_refs": Array<string>;
  "evidence_refs": Array<string>;
  "final_justification": string;
  "final_scores": {
    "originality": number;
    "overall": number;
    "presentation": number;
    "significance": number;
    "soundness": number;
  };
  "frozen_at": string;
  "official_review_version": 1;
  "remaining_concerns": Array<string>;
  "resolved_concerns": Array<string>;
  "reviewer_id": string;
  "version": 1;
};

export type Followup = {
  "concern_resolutions": Array<Record<string, unknown>>;
  "confidence": number;
  "evidence_refs": Array<string>;
  "new_questions": Array<string>;
  "official_review_version": 1;
  "rebuttal_version": number;
  "reviewer_id": string;
  "score_change_rationale": string;
  "scores": {
    "originality": number;
    "overall": number;
    "presentation": number;
    "significance": number;
    "soundness": number;
  };
  "summary": string;
  "version": 1;
};

export type FreezeRecord = {
  "extraction_tool": {
    "name": string;
    "version": string;
  };
  "freeze_hash": string;
  "frozen_at": string;
  "inputs": Array<{
    "path": string;
    "sha256": string;
    "size_bytes": number;
  }>;
  "literature_cutoff": string;
  "repository_commit": string | null;
  "review_start_time": string;
  "run_config_hash": string;
  "run_id": string;
  "schema_version": 1;
};

export type Identity = {
  "agent_id": string;
  "created_at": string;
  "identity_version": 1;
  "retired_at"?: string | null;
  "role": "reviewer" | "author" | "ac" | "sac" | "pc" | "validator" | "extractor" | "watchdog";
  "role_instance_id": string;
  "run_id": string;
};

export type InvocationResult = {
  "agent_id": string;
  "allowed_input_manifest_hash": string;
  "artifact_hash": string | null;
  "artifact_path": string;
  "completed_at": string;
  "exit_code": number;
  "phase": string;
  "promise": "NEXT" | "COMPLETE" | "BLOCKED" | null;
  "reason": string | null;
  "role": "reviewer" | "author" | "ac" | "sac" | "pc" | "validator" | "extractor" | "watchdog";
  "schema_version": 1;
  "status": "settled" | "reopen" | "blocked" | "policy_blocked" | "agent_failed" | "time_exhausted" | "interrupted";
};

export type LiteratureRegistry = {
  "agent_id": string;
  "entries": Array<{
    "completed_at"?: string | null;
    "failure_reason"?: string | null;
    "query": string;
    "query_id": string;
    "reason"?: string;
    "requested_at"?: string;
    "results": Array<{
      "admissibility"?: "admissible_prior_work" | "admissible_background" | "inadmissible_post_cutoff" | "quarantined_target_duplicate" | "unverified";
      "canonical_uri": string;
      "content_hash"?: string | null;
      "evidence_packet_path"?: string | null;
      "first_public_date"?: string;
      "source_id": string;
      "title": string;
      "verification_status"?: "metadata_only" | "abstract_checked" | "full_text_checked" | "source_inaccessible";
    }>;
    "status": "pending" | "running" | "completed" | "failed";
  }>;
  "schema_version": 1;
  "version": number;
};

export type MathematicalClaimInventory = {
  "claims": Array<{
    "anchor_id": string;
    "id": string;
    "page"?: number;
    "statement": string;
  }>;
  "counts": {
    "claims": number;
    "equations": number;
    "theorems": number;
  };
  "schema_version": 1;
  "submission_id": string;
};

export type MathematicalConfirmationReport = {
  "checked_findings": number;
  "high_impact_negative_findings": Array<string>;
  "schema_version": 1;
  "status": "passed";
};

export type MathematicalFindingLedger = {
  "agent_id": string;
  "findings": Array<string>;
  "schema_version": 1;
};

export type MathematicalFormalProofResult = {
  "claim_id": string;
  "compiler_exit_code": number | null;
  "compiler_stderr": string;
  "compiler_stdout": string;
  "formalization_fidelity": "aligned" | "mismatch" | "not_assessed";
  "formalization_sha256": string;
  "paper_anchors": Array<string>;
  "proof_attempted": boolean;
  "proof_compiled": boolean;
  "proof_validity": "accepted" | "rejected" | "inconclusive" | "tool_unsupported";
  "protocol_note": "Lean proof accepted does not imply that the paper theorem was verified.";
  "statement_alignment": "aligned" | "mismatch";
  "statement_alignment_checked": true;
  "statement_alignment_evidence": string;
  "toolchain_image": string;
  "toolchain_version": string;
};

export type MathematicalToolEvidence = unknown | unknown | unknown | unknown | unknown | unknown | unknown;

export type MathematicalValidationBundle = {
  "agent_id": string;
  "finding_count": number;
  "findings": Array<ValidationFinding>;
  "phase_order": unknown;
  "published_at": string;
  "run_id": string;
  "schema_version": 1;
  "submission_id": string;
};

export type MetaReview = {
  "ac_id": string;
  "agreed_strengths": Array<string>;
  "confidence": number;
  "constructive_next_steps": Array<string>;
  "decisive_concerns": Array<string>;
  "evidence_refs": Array<string>;
  "main_contribution": string;
  "published_at": string;
  "rebuttal_effect": string;
  "recommendation": "accept" | "reject";
  "remaining_issues": Array<string>;
  "reviewer_disagreement": string;
  "validation_evidence": string;
  "version": 1;
};

export type OfficialReview = {
  "confidence": number;
  "ethical_concerns": Array<string>;
  "evidence_refs": Array<string>;
  "key_questions": Array<{
    "id": string;
    "possible_score_impact": string;
    "question": string;
  }>;
  "limitations": string;
  "reviewer_id": string;
  "scores": {
    "originality": number;
    "overall": number;
    "presentation": number;
    "significance": number;
    "soundness": number;
  };
  "strengths": Array<{
    "anchors": Array<string>;
    "text": string;
  }>;
  "summary": string;
  "version"?: 1;
  "weaknesses": Array<{
    "affected_claims": Array<string>;
    "anchors": Array<string>;
    "id": string;
    "severity": "minor" | "major" | "critical";
    "text": string;
  }>;
};

export type PaperDossier = {
  "ambiguities": Array<string>;
  "baselines": Array<Record<string, unknown>>;
  "claims": Array<Record<string, unknown>>;
  "contributions": Array<Record<string, unknown>>;
  "datasets": Array<Record<string, unknown>>;
  "dossier_version": 1;
  "equations": Array<Record<string, unknown>>;
  "ethical_risk_triggers": Array<string>;
  "experiments": Array<Record<string, unknown>>;
  "limitations": Array<string>;
  "method_graph": Array<Record<string, unknown>>;
  "metrics": Array<Record<string, unknown>>;
  "references": Array<Record<string, unknown>>;
  "reported_results": Array<Record<string, unknown>>;
  "reproducibility": Array<Record<string, unknown>>;
  "submission_id": string;
  "theorems": Array<Record<string, unknown>>;
};

export type ParseVerificationReport = {
  "checks": Array<{
    "duplicates": Array<string>;
    "name": "inline_anchor_resolution";
    "status": "passed" | "failed";
    "unresolved": Array<string>;
  } | {
    "name": "anchor_inventory";
    "orphaned": Array<string>;
    "status": "passed" | "failed";
  } | {
    "malformed": Array<string>;
    "name": "provenance_records";
    "status": "passed" | "failed";
  } | {
    "missing": Array<string>;
    "name": "asset_resolution";
    "status": "passed" | "failed";
    "unsafe": Array<string>;
  } | {
    "failures": Array<string>;
    "name": "heading_equation_table_structure";
    "status": "passed" | "failed";
  } | {
    "failed_anchor_ids": Array<string>;
    "minimum_overlap": number;
    "name": "sampled_text_overlap";
    "reason": null | "source_text_by_page_required";
    "samples": Array<{
      "anchor_id": string;
      "status": "not_run";
    } | {
      "anchor_id": string;
      "overlap": number;
      "page": number;
      "status": "checked";
    }>;
    "status": "passed" | "failed";
  }>;
  "failed_checks": Array<"inline_anchor_resolution" | "anchor_inventory" | "provenance_records" | "asset_resolution" | "heading_equation_table_structure" | "sampled_text_overlap">;
  "orphan_anchor_ids": Array<string>;
  "sample_size": number;
  "schema_version": "1.0";
  "status": "passed" | "failed";
  "unresolved_anchor_count": number;
  "unresolved_anchor_ids": Array<string>;
  "verified_bundle": {
    "bundle_sha256": string;
    "files": Array<{
      "path": string;
      "sha256": string;
      "size_bytes": number;
    }>;
  };
};

export type Persona = {
  "communication_style": string;
  "confidence_policy": string;
  "decision_bias": "neutral";
  "familiarity": {
    [key: string]: "none" | "low" | "medium" | "high" | "very_high";
  };
  "known_blind_spots": Array<string>;
  "likely_deep_dive_areas": Array<string>;
  "persona_version"?: 1;
  "primary_expertise": Array<string>;
  "reviewer_id": string;
  "secondary_expertise": Array<string>;
};

export type PhaseState = {
  "agent_id"?: string;
  "allowed_input_manifest_hash"?: string;
  "attempt": number;
  "attempt_count"?: number;
  "completed_at"?: string | null;
  "current_task": string | null;
  "failure_category"?: string | null;
  "heartbeat_at"?: string;
  "input_manifest_hash"?: string;
  "last_artifact_hash": string | null;
  "last_artifact_id"?: string | null;
  "last_promise"?: "NEXT" | "COMPLETE" | "BLOCKED" | null;
  "next_eligible_at"?: string | null;
  "no_progress_count": number;
  "phase": string;
  "phase_run_id"?: string;
  "pid"?: number | null;
  "reason"?: string | null;
  "reopen_category"?: string | null;
  "reopen_reason"?: string | null;
  "role"?: "reviewer" | "author" | "ac" | "sac" | "pc" | "validator" | "extractor" | "watchdog";
  "run_id"?: string;
  "started_at"?: string;
  "status": "pending" | "running" | "blocked" | "completed" | "failed" | "stalled";
  "updated_at"?: string;
};

export type PhaseTasks = {
  "current_task_id"?: string | null;
  "phase"?: string;
  "schema_version"?: 1;
  "tasks": Array<{
    "attempt_count"?: number;
    "blocked_reason"?: string | null;
    "completed_at"?: string | null;
    "completion_predicate"?: string;
    "description"?: string;
    "id": string;
    "inputs"?: Array<string>;
    "output_path"?: string;
    "retry_feedback"?: string | null;
    "status": "pending" | "in_progress" | "completed" | "blocked";
    "type"?: string;
  }>;
};

export type QuestionLedger = {
  "ledger_version": number;
  "questions": Array<{
    "answer_refs"?: Array<string>;
    "id": string;
    "possible_score_impact": string;
    "question": string;
    "status": "open" | "answered" | "partially_answered" | "unresolved" | "withdrawn";
  }>;
  "reviewer_id": string;
};

export type Rebuttal = {
  "commitments": Array<string>;
  "evidence_refs": Array<string>;
  "limitations_acknowledged": Array<string>;
  "official_review_version": 1;
  "published_at": string;
  "responses": Array<{
    "concern_id": string;
    "evidence_refs": Array<string>;
    "response": string;
    "response_label": "already_in_paper" | "clarification" | "submitted_additional_evidence" | "limitation_acknowledged" | "planned_revision" | "cannot_answer_without_new_research";
  }>;
  "reviewer_id": string;
  "version": 1;
};

export type ResponseMatrix = {
  "author_evidence_type": "already_in_paper" | "clarification" | "submitted_additional_evidence" | "limitation_acknowledged" | "planned_revision" | "cannot_answer_without_new_research";
  "available_paper_evidence": Array<string>;
  "commitments": Array<string>;
  "concern_id": string;
  "concern_type": string;
  "contradiction_risk": boolean;
  "draft_answer": string;
  "duplicate_concerns": Array<string>;
  "requested_evidence": string;
  "reviewer_id": string;
  "status": "pending" | "drafting" | "ready" | "published" | "unresolved";
};

export type RoleState = {
  "agent_id": string;
  "completed_phases": Array<string>;
  "concern_ledger_version"?: number;
  "current_phase": string;
  "current_review_version"?: number;
  "official_review_version"?: number;
  "persona_version"?: number;
  "role": "reviewer" | "author" | "ac" | "sac" | "pc" | "validator" | "extractor" | "watchdog";
  "score_history_version"?: number;
  "status": "pending" | "running" | "blocked" | "completed" | "failed" | "stalled";
};

export type RunBudget = {
  "deadline_at": string;
  "discussion_rounds": {
    [key: string]: number;
  };
  "last_artifact_hashes": {
    [key: string]: string;
  };
  "limits": {
    "max_ac_restarts"?: number;
    "max_author_restarts"?: number;
    "max_budget_usd"?: number;
    "max_discussion_rounds"?: number;
    "max_restarts"?: number;
    "max_reviewer_restarts"?: number;
    "max_validator_restarts"?: number;
    "no_progress_threshold"?: number;
  };
  "no_progress_counts": {
    [key: string]: number;
  };
  "restart_counts": {
    [key: string]: number;
  };
  "schema_version"?: 1;
  "spent_usd"?: number;
  "started_at": string;
  "subscription_cursors": {
    [key: string]: string | number | null;
  };
  "updated_at"?: string;
};

export type RunConfig = {
  "block_camera_ready_version"?: boolean;
  "block_decision"?: boolean;
  "block_exact_target_title_search"?: boolean;
  "block_human_reviews"?: boolean;
  "block_meta_review"?: boolean;
  "block_openreview"?: boolean;
  "block_post_cutoff_sources"?: boolean;
  "block_private_track1_data"?: boolean;
  "block_rebuttals"?: boolean;
  "block_target_authors"?: boolean;
  "block_target_duplicates"?: boolean;
  "block_target_preprint"?: boolean;
  "config_version": 1;
  "freeze_literature_snapshot"?: boolean;
  "literature_cutoff": string;
  "max_ac_restarts"?: number;
  "max_author_restarts"?: number;
  "max_budget_usd"?: number;
  "max_discussion_rounds"?: number;
  "max_reviewer_restarts"?: number;
  "max_validator_restarts"?: number;
  "max_wall_clock_hours"?: number;
  "mode": "historical_benchmark" | "current_blind_submission" | "live_submission" | "batch_conference";
  "no_progress_threshold"?: number;
  "privacy_mode"?: "strict" | "standard";
  "review_start_time": string;
  "reviewer_count": number;
  "run_id": string;
  "stable_score_rounds"?: number;
  "submission_manifest_path": string;
};

export type RunState = {
  "failure_reason"?: string;
  "run_id": string;
  "state": "CREATED" | "INGESTING" | "DOSSIER" | "PERSONA_ASSIGNMENT" | "PRELIMINARY_REVIEW" | "VALIDATION" | "OFFICIAL_REVIEW" | "AUTHOR_REBUTTAL" | "REVIEWER_FOLLOWUP" | "AUTHOR_FINAL" | "INTERNAL_DISCUSSION" | "AC_META_REVIEW" | "SAC_CALIBRATION" | "PC_FINALIZATION" | "COMPLETE" | "INPUT_INVALID" | "POLICY_BLOCKED" | "AGENT_FAILED" | "VALIDATION_FAILED" | "STALLED" | "TIME_EXHAUSTED" | "BUDGET_EXHAUSTED" | "INCOMPLETE";
  "state_version": number;
  "updated_at": string;
};

export type ScoreHistory = {
  "append_only": true;
  "entries": Array<{
    "confidence": number;
    "entry_hash": string;
    "entry_id": string;
    "phase": "initial_review" | "followup" | "discussion" | "final_justification";
    "previous_entry_hash"?: string | null;
    "rationale": string;
    "recorded_at": string;
    "scores": {
      "originality": number;
      "overall": number;
      "presentation": number;
      "significance": number;
      "soundness": number;
    };
  }>;
  "history_id": string;
  "prior_version_hash"?: string | null;
  "reviewer_id": string;
  "version": number;
};

export type SemanticCoverageLedger = {
  "dossier_hash": unknown;
  "extraction_anchor_catalog_hash": unknown;
  "frozen_input_hash": unknown;
  "inventory": {
    "page_count": number;
    "section_ids": Array<string>;
    "supplements": Array<{
      "content_hash": unknown;
      "supplement_id": string;
    }>;
  };
  "ledger_hash": unknown;
  "run_id": string;
  "schema_version": 1;
  "units": Array<unknown>;
};

export type SubmissionManifest = {
  "authors_visible": boolean;
  "consent_to_process": true;
  "paper_path": string;
  "repository": {
    "commit": string | null;
    "officiality": "official" | "unofficial" | "unknown";
    "url": string | null;
  };
  "review_mode": "historical_blind" | "current_blind_submission" | "live_submission" | "batch_conference";
  "submission_id": string;
  "supplement_paths": Array<string>;
  "title": string;
  "track": string;
  "venue": string;
  "year": number;
};

export type TableAsset = {
  "anchor_id": string;
  "caption": string;
  "rows": Array<Array<string>>;
};

export type TaskContext = {
  "attempt"?: number;
  "completion_predicate"?: string;
  "inputs"?: Array<string | {
    "category"?: string;
    "path": string;
  }>;
  "max_attempts"?: number;
  "output_path"?: string;
  "output_schema"?: string;
  "phase"?: string;
  "retry_feedback"?: string | null;
  "schema_version"?: 1;
  "task"?: string | null;
  "task_id"?: string;
  "type"?: string;
};

export type TerminalArmInput = {
  "arm_cohort_id": string;
  "campaign_id": string;
  "slots": Array<{
    "meta_review": MetaReview;
    "meta_review_hash": string;
    "meta_review_ref": string;
    "paper_id": string;
    "paper_slot": number;
    "status": "meta_review";
    "validation": {
      "passed": true;
      "schema_id": string;
      "validated_at": string;
      "validator_id": string;
    };
  } | {
    "failure": {
      "code": string;
      "evidence_refs": Array<string>;
      "message": string;
      "occurred_at": string;
      "stage": string;
    };
    "paper_id": string;
    "paper_slot": number;
    "status": "paper_failure";
  }>;
  "version": 1;
};

export type FrozenValidationBundle = {
  "bundle_version": 1;
  "conflicts": Array<{
    "claim_id": string;
    "finding_ids": Array<string>;
    "resolution": "surfaced_not_averaged";
    "statuses": Array<unknown>;
  }>;
  "content_hash": string;
  "findings": Array<ValidationFinding>;
  "frozen_at": string;
  "source_lanes": Array<"g1-code" | "g2-mathematics" | "g3-statistics" | "g3-references" | "g3-ethics">;
  "submission_id": string;
};

export type ValidationFinding = {
  "artifact_refs"?: Array<string>;
  "claim_id": string | null;
  "confidence": number;
  "confirmation_paths": Array<string>;
  "finding_id": string;
  "limitations": string;
  "method": string;
  "observation": string;
  "paper_anchors": Array<string>;
  "severity_candidate": "none" | "minor" | "major" | "critical";
  "status": "verified_formally" | "verified_symbolically" | "verified_exactly" | "supported_numerically" | "counterexample_found" | "missing_assumption" | "statement_mismatch" | "equation_code_mismatch" | "partially_verified" | "inconclusive" | "tool_unsupported" | "not_attempted" | "artifacts_inspected" | "environment_built" | "partial_execution" | "key_result_reproduced" | "full_claim_set_reproduced" | "independently_reimplemented" | "execution_failed" | "not_executable" | "verified_exact" | "verified_with_minor_metadata_difference" | "verified_preprint_only" | "verified_different_version" | "metadata_mismatch" | "duplicate_reference" | "unresolved" | "likely_nonexistent" | "confirmed_nonexistent" | "directly_supports" | "supports_with_qualification" | "partially_supports" | "background_only" | "does_not_support" | "contradicts" | "source_never_makes_claim" | "source_inaccessible" | "current" | "corrected" | "retracted" | "withdrawn" | "superseded" | "expression_of_concern" | "version_mismatch" | "unknown";
  "validator_type": "code" | "clean_room" | "conformance" | "formal_math" | "symbolic_math" | "exact_math" | "numerical_math" | "statistics" | "reproducibility" | "reference_identity" | "citation_support" | "publication_status" | "ethics_integrity";
};

export type WatchdogConfig = {
  "advance_empty_states"?: boolean;
  "auto_advance_run_state"?: boolean;
  "complete_when_all_phases"?: boolean;
  "facts"?: {
    [key: string]: boolean;
  };
  "initial_backoff_seconds"?: number;
  "initial_run_state"?: string;
  "initial_state"?: string;
  "max_backoff_seconds"?: number;
  "phase_runs": Array<{
    "agent_args"?: Array<string>;
    "agent_command"?: string;
    "agent_id": string;
    "allow"?: Array<string>;
    "artifact"?: string;
    "artifact_validator"?: string;
    "artifacts_are_validated"?: boolean;
    "completion_gates"?: Array<string | {
      "field"?: string;
      "path"?: string;
      "pattern"?: string;
      "type": "file_exists" | "json_equals" | "event_seen";
      "value"?: unknown;
    }>;
    "current_task_context"?: TaskContext;
    "gates"?: Array<string | {
      "field"?: string;
      "path"?: string;
      "pattern"?: string;
      "type": "file_exists" | "json_equals" | "event_seen";
      "value"?: unknown;
    }>;
    "ledgers"?: Array<string>;
    "literature_registry"?: LiteratureRegistry;
    "manifest_generator"?: string;
    "output_schema"?: string;
    "persona"?: Persona;
    "phase": string;
    "phase_prompt"?: string;
    "policy"?: string;
    "publication_paths"?: Array<string>;
    "publish_path"?: string;
    "requires_artifact"?: boolean;
    "response_matrix"?: ResponseMatrix;
    "role": "reviewer" | "author" | "ac" | "sac" | "pc" | "validator" | "extractor" | "watchdog";
    "role_instance_id"?: string;
    "role_prompt"?: string;
    "rubric"?: string;
    "run_states"?: Array<"CREATED" | "INGESTING" | "DOSSIER" | "PERSONA_ASSIGNMENT" | "PRELIMINARY_REVIEW" | "VALIDATION" | "OFFICIAL_REVIEW" | "AUTHOR_REBUTTAL" | "REVIEWER_FOLLOWUP" | "AUTHOR_FINAL" | "INTERNAL_DISCUSSION" | "AC_META_REVIEW" | "SAC_CALIBRATION" | "PC_FINALIZATION" | "COMPLETE">;
    "runner_interface"?: string;
    "schema"?: string;
    "score_history"?: ScoreHistory;
    "subscriptions"?: Array<string | {
      "event"?: string;
      "path"?: string;
    }>;
    "task_context"?: string;
    "tasks_template"?: string;
    "timeout_seconds"?: number;
    "use_contract_manifest"?: boolean;
  }>;
  "poll_seconds"?: number;
  "run_id"?: string;
  "run_state"?: string;
  "run_state_gates"?: {
    [key: string]: Array<string | {
      "field"?: string;
      "path"?: string;
      "pattern"?: string;
      "type": "file_exists" | "json_equals" | "event_seen";
      "value"?: unknown;
    }>;
  };
  "runner"?: string;
  "safety"?: {
    "max_ac_restarts"?: number;
    "max_author_restarts"?: number;
    "max_budget_usd"?: number;
    "max_discussion_rounds"?: number;
    "max_restarts"?: number;
    "max_restarts_per_role"?: number;
    "max_reviewer_restarts"?: number;
    "max_validator_restarts"?: number;
    "max_wall_clock_hours"?: number;
    "max_wall_clock_seconds"?: number;
    "no_progress_threshold"?: number;
  };
  "schema_version"?: 1;
};

export type WatchdogStatus = {
  "budget"?: {
    "deadline_at"?: string;
    "discussion_rounds"?: number;
    "max_budget_usd"?: number;
    "no_progress_count"?: number;
    "restart_count"?: number;
    "spent_usd"?: number;
  };
  "reason": string | null;
  "resumed_at"?: string;
  "run_state": "CREATED" | "INGESTING" | "DOSSIER" | "PERSONA_ASSIGNMENT" | "PRELIMINARY_REVIEW" | "VALIDATION" | "OFFICIAL_REVIEW" | "AUTHOR_REBUTTAL" | "REVIEWER_FOLLOWUP" | "AUTHOR_FINAL" | "INTERNAL_DISCUSSION" | "AC_META_REVIEW" | "SAC_CALIBRATION" | "PC_FINALIZATION" | "COMPLETE" | "AGENT_FAILED" | "STALLED" | "TIME_EXHAUSTED" | "BUDGET_EXHAUSTED" | "POLICY_BLOCKED";
  "schema_version"?: 1;
  "started_at": string;
  "status": "RUNNING" | "SUCCESS" | "INCOMPLETE" | "STALLED" | "BLOCKED" | "FAILED" | "TIME_EXHAUSTED" | "BUDGET_EXHAUSTED" | "POLICY_BLOCKED";
  "updated_at"?: string;
  "watchdog_pid"?: number;
};
