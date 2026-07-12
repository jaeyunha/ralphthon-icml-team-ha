"""CLI for broker mailbox preparation and bibliography-result validation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .validator import build_broker_requests, validate_references


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def prepare(args: argparse.Namespace) -> None:
    dossier = _read(args.dossier)
    fingerprint_doc = _read(args.fingerprint)
    target = fingerprint_doc.get("targetFingerprint", fingerprint_doc)
    if not isinstance(target, dict):
        raise ValueError("target fingerprint must be an object")
    requests = build_broker_requests(
        dossier,
        target,
        run_id=args.run_id,
        reviewer_id=args.reviewer_id,
        literature_cutoff=args.cutoff,
    )
    outbox = args.workspace / "outbox" / "literature"
    outbox.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, str] = {}
    references = dossier.get("references", [])
    for request, reference in zip(requests, references, strict=True):
        request_id = str(request["requestId"])
        reference_id = str(reference["id"])
        mapping[request_id] = reference_id
        (outbox / f"{request_id}.json").write_text(
            json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    args.mapping.write_text(json.dumps(mapping, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"prepared": len(requests), "outbox": str(outbox)}))


def analyze(args: argparse.Namespace) -> None:
    dossier = _read(args.dossier)
    mapping = _read(args.mapping)
    broker_results: dict[str, dict[str, object]] = {}
    for request_id, reference_id in mapping.items():
        path = args.workspace / "inbox" / "literature" / f"{request_id}.json"
        if path.is_file():
            broker_results[str(reference_id)] = _read(path)
    report = validate_references(dossier, broker_results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"validated": len(broker_results), "findings": len(report["findings"])}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--dossier", type=Path, required=True)
    prepare_parser.add_argument("--fingerprint", type=Path, required=True)
    prepare_parser.add_argument("--workspace", type=Path, required=True)
    prepare_parser.add_argument("--mapping", type=Path, required=True)
    prepare_parser.add_argument("--run-id", required=True)
    prepare_parser.add_argument("--reviewer-id", required=True)
    prepare_parser.add_argument("--cutoff", required=True)
    prepare_parser.set_defaults(handler=prepare)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--dossier", type=Path, required=True)
    analyze_parser.add_argument("--workspace", type=Path, required=True)
    analyze_parser.add_argument("--mapping", type=Path, required=True)
    analyze_parser.add_argument("--output", type=Path, required=True)
    analyze_parser.set_defaults(handler=analyze)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
