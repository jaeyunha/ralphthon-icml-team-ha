"""Canonical submission extraction, verification, and dossier helpers."""

from .coverage_ledger import (
    build_coverage_ledger,
    canonical_json_bytes,
    coverage_ledger_hash,
    verify_coverage_ledger,
)

from .dossier import (
    DossierGateError,
    build_dossier,
    validate_dossier_anchors,
    verified_bundle_from_dossier,
)
from .extract import ExtractionError, extract_pdf, extract_to_bundle
from .freeze import (
    BundleValidationError,
    FreezeError,
    FreezeRecordError,
    MutationDetectedError,
    SubmissionBundle,
    UnsafePathError,
    assert_submission_unchanged,
    build_freeze_record,
    freeze_submission,
    load_freeze_record,
    validate_submission_bundle,
    verify_frozen_submission,
)
from .parse_verification import bundle_identity, pdf_text_by_page, verify_bundle

__all__ = [
    "BundleValidationError",
    "DossierGateError",
    "ExtractionError",
    "FreezeError",
    "FreezeRecordError",
    "MutationDetectedError",
    "SubmissionBundle",
    "UnsafePathError",
    "assert_submission_unchanged",
    "bundle_identity",
    "build_dossier",
    "build_freeze_record",
    "build_coverage_ledger",
    "canonical_json_bytes",
    "coverage_ledger_hash",

    "extract_pdf",
    "extract_to_bundle",
    "freeze_submission",
    "load_freeze_record",
    "pdf_text_by_page",
    "validate_dossier_anchors",
    "validate_submission_bundle",
    "verify_bundle",
    "verify_coverage_ledger",
    "verified_bundle_from_dossier",
    "verify_frozen_submission",
]
