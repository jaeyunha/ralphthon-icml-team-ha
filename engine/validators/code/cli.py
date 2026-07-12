from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

from .reproduction import OfficialReproducer, ReproductionCommand, write_report_atomic


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the code-validation official reproduction loop"
    )
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--provenance", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--documentation-scale", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument(
        "--command",
        action="append",
        required=True,
        help="JSON object with name, argv, and optional timeout_seconds",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    commands: list[ReproductionCommand] = []
    for encoded in args.command:
        payload = json.loads(encoded)
        commands.append(
            ReproductionCommand(
                name=payload["name"],
                argv=tuple(payload["argv"]),
                timeout_seconds=float(payload.get("timeout_seconds", 60)),
            )
        )
    report = OfficialReproducer().run(
        paper_id=args.paper_id,
        repository=args.repository,
        provenance=args.provenance,
        image=args.image,
        commands=commands,
        documentation_scale=args.documentation_scale,
        hardware={
            "host_platform": platform.platform(),
            "machine": platform.machine(),
            "accelerator": "none",
        },
    )
    write_report_atomic(report, args.output)
    print(json.dumps({"output": str(args.output), "status": report["reproducibility_audit"]}))
    return 0
