"""CLI for freezing cross-lane validation bundles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .bundle import arbitrate_findings


def _findings(path: Path) -> list[object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("findings"), list):
        return value["findings"]
    raise ValueError(f"{path} must contain a finding array or an object with findings")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--submission-id", required=True)
    parser.add_argument("--lane", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--frozen-at")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lanes: dict[str, list[object]] = {}
    for item in args.lane:
        name, separator, raw_path = item.partition("=")
        if not separator or not name or not raw_path:
            parser.error(f"invalid --lane {item!r}; expected NAME=PATH")
        lanes[name] = _findings(Path(raw_path))
    bundle = arbitrate_findings(args.submission_id, lanes, frozen_at=args.frozen_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "findings": len(bundle["findings"]),
                "conflicts": len(bundle["conflicts"]),
                "content_hash": bundle["content_hash"],
            }
        )
    )


if __name__ == "__main__":
    main()
