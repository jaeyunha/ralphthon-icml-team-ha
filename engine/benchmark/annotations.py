"""Frozen dossier claim units and deterministic proposition-aware annotation matching."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Iterable, Mapping, Sequence


class AnnotationValidationError(ValueError):
    """Raised when claim units or annotation records violate the frozen codebook."""


class AnnotationKind(StrEnum):
    STRENGTH = "strength"
    CONCERN = "concern"
    NEUTRAL = "neutral"


class ResolutionStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    UNRESOLVED = "unresolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    RESOLVED = "resolved"
    INVALIDATED = "invalidated"


class PropositionRelation(StrEnum):
    EQUIVALENT = "equivalent"
    GENERATED_ENTAILS_GOLD = "generated_entails_gold"
    GOLD_ENTAILS_GENERATED = "gold_entails_generated"
    UNRELATED = "unrelated"


CONFIRMED_PROPOSITION_RELATIONS = frozenset(
    {
        PropositionRelation.EQUIVALENT,
        PropositionRelation.GENERATED_ENTAILS_GOLD,
        PropositionRelation.GOLD_ENTAILS_GENERATED,
    }
)


@dataclass(frozen=True, slots=True)
class ClaimUnit:
    claim_id: str
    normalized_proposition: str
    scope: str
    anchor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.claim_id or not self.normalized_proposition or not self.scope:
            raise AnnotationValidationError("claim_id, normalized_proposition, and scope are required")
        if not self.anchor_ids or any(not anchor for anchor in self.anchor_ids):
            raise AnnotationValidationError("claim units require at least one stable anchor")
        if tuple(sorted(set(self.anchor_ids))) != self.anchor_ids:
            raise AnnotationValidationError("claim unit anchors must be unique and sorted")


@dataclass(frozen=True, slots=True)
class AnnotationItem:
    annotation_id: str
    claim_id: str
    kind: AnnotationKind
    severity: int | None
    normalized_proposition: str
    scope: str
    anchors: tuple[str, ...]
    valid_anchors: tuple[str, ...] = ()
    material_assertion: bool = True
    is_new_followup_question: bool = False
    answer_induced: bool | None = None
    terminal_resolution_status: ResolutionStatus = ResolutionStatus.NOT_APPLICABLE

    def __post_init__(self) -> None:
        if not self.annotation_id or not self.claim_id or not self.normalized_proposition:
            raise AnnotationValidationError("annotation_id, claim_id, and proposition are required")
        if not self.scope:
            raise AnnotationValidationError("annotation scope is required")
        if self.kind is AnnotationKind.NEUTRAL:
            if self.severity is not None:
                raise AnnotationValidationError("neutral annotations must have missing severity")
        elif self.severity not in {1, 2, 3}:
            raise AnnotationValidationError("strength and concern severity must be 1 through 3")
        if tuple(sorted(set(self.anchors))) != self.anchors:
            raise AnnotationValidationError("annotation anchors must be unique and sorted")
        if tuple(sorted(set(self.valid_anchors))) != self.valid_anchors:
            raise AnnotationValidationError("valid anchors must be unique and sorted")
        if not set(self.valid_anchors).issubset(self.anchors):
            raise AnnotationValidationError("valid anchors must be a subset of cited anchors")
        if self.is_new_followup_question and self.answer_induced is None:
            raise AnnotationValidationError("new follow-up questions require answer_induced")
        if not self.is_new_followup_question and self.answer_induced is not None:
            raise AnnotationValidationError("answer_induced is only valid for new follow-up questions")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> AnnotationItem:
        """Parse one fixture or frozen annotation record using the strict codebook."""

        anchors = _strings(value.get("anchors", ()))
        valid_anchors = _strings(value.get("valid_anchors", ()))
        severity_value = value.get("severity")
        if severity_value is not None and (
            not isinstance(severity_value, int) or isinstance(severity_value, bool)
        ):
            raise AnnotationValidationError("severity must be an integer or null")
        answer_induced = value.get("answer_induced")
        if answer_induced is not None and not isinstance(answer_induced, bool):
            raise AnnotationValidationError("answer_induced must be boolean or null")
        return cls(
            annotation_id=_required_string(value, "annotation_id"),
            claim_id=_required_string(value, "claim_id"),
            kind=AnnotationKind(_required_string(value, "kind")),
            severity=severity_value,
            normalized_proposition=_required_string(value, "normalized_proposition"),
            scope=_required_string(value, "scope"),
            anchors=anchors,
            valid_anchors=valid_anchors,
            material_assertion=_boolean(value, "material_assertion", True),
            is_new_followup_question=_boolean(value, "is_new_followup_question", False),
            answer_induced=answer_induced,
            terminal_resolution_status=ResolutionStatus(
                str(value.get("terminal_resolution_status", ResolutionStatus.NOT_APPLICABLE.value))
            ),
        )


@dataclass(frozen=True, slots=True, order=True)
class AnnotationMatch:
    gold_id: str
    generated_id: str
    weight: int

    def __post_init__(self) -> None:
        if not self.gold_id or not self.generated_id or self.weight <= 0:
            raise AnnotationValidationError("matches require identifiers and positive weight")


def claim_units_from_dossier(dossier: Mapping[str, object]) -> tuple[ClaimUnit, ...]:
    """Freeze the dossier claim inventory as the common annotation universe."""

    raw_claims = dossier.get("claims")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise AnnotationValidationError("dossier claims must be a nonempty list")
    units: list[ClaimUnit] = []
    for raw in raw_claims:
        if not isinstance(raw, Mapping):
            raise AnnotationValidationError("every dossier claim must be an object")
        claim_id = _required_string(raw, "claim_id", fallback="id")
        proposition = _first_string(
            raw,
            ("normalized_proposition", "proposition", "statement"),
        )
        scope = _scope(raw.get("scope", "paper"))
        anchors = _claim_anchors(raw)
        units.append(ClaimUnit(claim_id, proposition, scope, anchors))
    units.sort(key=lambda unit: unit.claim_id)
    if len({unit.claim_id for unit in units}) != len(units):
        raise AnnotationValidationError("dossier claim identifiers must be unique")
    return tuple(units)


def claim_inventory_hash(units: Sequence[ClaimUnit]) -> str:
    """Return the content hash that binds the common annotation units."""

    payload = [asdict(unit) for unit in sorted(units, key=lambda item: item.claim_id)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_gold_inventory(
    units: Sequence[ClaimUnit],
    annotations: Sequence[AnnotationItem],
) -> None:
    """Require exactly one gold category record for every frozen dossier claim."""

    expected = {unit.claim_id for unit in units}
    actual = [annotation.claim_id for annotation in annotations]
    if len(actual) != len(set(actual)):
        raise AnnotationValidationError("gold annotations must contain one item per claim")
    if set(actual) != expected:
        missing = sorted(expected - set(actual))
        extra = sorted(set(actual) - expected)
        raise AnnotationValidationError(f"gold inventory mismatch; missing={missing}, extra={extra}")


def validate_generated_claims(
    units: Sequence[ClaimUnit],
    annotations: Sequence[AnnotationItem],
) -> None:
    """Require every generated item to map to exactly one frozen claim identifier."""

    known = {unit.claim_id for unit in units}
    unknown = sorted({item.claim_id for item in annotations} - known)
    if unknown:
        raise AnnotationValidationError(f"generated annotations reference unknown claims: {unknown}")
    if len({item.annotation_id for item in annotations}) != len(annotations):
        raise AnnotationValidationError("generated annotation identifiers must be unique")


def proposition_aware_matching(
    gold: Sequence[AnnotationItem],
    generated: Sequence[AnnotationItem],
    judgments: Mapping[tuple[str, str], PropositionRelation],
) -> tuple[AnnotationMatch, ...]:
    """Compute maximum-weight one-to-one matches with the frozen global tie rule."""

    if len({item.annotation_id for item in gold}) != len(gold):
        raise AnnotationValidationError("gold annotation identifiers must be unique")
    if len({item.annotation_id for item in generated}) != len(generated):
        raise AnnotationValidationError("generated annotation identifiers must be unique")

    grouped_gold: dict[tuple[str, AnnotationKind], list[AnnotationItem]] = {}
    grouped_generated: dict[tuple[str, AnnotationKind], list[AnnotationItem]] = {}
    for item in gold:
        grouped_gold.setdefault((item.claim_id, item.kind), []).append(item)
    for item in generated:
        grouped_generated.setdefault((item.claim_id, item.kind), []).append(item)

    matches: list[AnnotationMatch] = []
    for group in sorted(set(grouped_gold).intersection(grouped_generated)):
        gold_group = sorted(grouped_gold[group], key=lambda item: item.annotation_id)
        generated_group = sorted(grouped_generated[group], key=lambda item: item.annotation_id)
        matches.extend(_best_group_matching(gold_group, generated_group, judgments))
    return tuple(sorted(matches, key=lambda item: (item.gold_id, item.generated_id)))


def _best_group_matching(
    gold: Sequence[AnnotationItem],
    generated: Sequence[AnnotationItem],
    judgments: Mapping[tuple[str, str], PropositionRelation],
) -> tuple[AnnotationMatch, ...]:
    edges: dict[tuple[int, int], int] = {}
    for gold_index, gold_item in enumerate(gold):
        for generated_index, generated_item in enumerate(generated):
            relation = judgments.get(
                (gold_item.annotation_id, generated_item.annotation_id),
                PropositionRelation.UNRELATED,
            )
            if relation not in CONFIRMED_PROPOSITION_RELATIONS:
                continue
            if not set(gold_item.anchors).intersection(generated_item.anchors):
                continue
            if not _severity_compatible(gold_item.severity, generated_item.severity):
                continue
            edges[(gold_index, generated_index)] = (
                4
                + 3
                + (2 if gold_item.severity == generated_item.severity else 0)
                + (1 if gold_item.scope == generated_item.scope else 0)
            )

    @lru_cache(maxsize=None)
    def choose(gold_index: int, used_generated: int) -> tuple[int, tuple[AnnotationMatch, ...]]:
        if gold_index >= len(gold):
            return 0, ()
        best_weight, best_matches = choose(gold_index + 1, used_generated)
        for generated_index, generated_item in enumerate(generated):
            if used_generated & (1 << generated_index):
                continue
            edge_weight = edges.get((gold_index, generated_index))
            if edge_weight is None:
                continue
            remaining_weight, remaining_matches = choose(
                gold_index + 1,
                used_generated | (1 << generated_index),
            )
            candidate_matches = tuple(
                sorted(
                    (
                        AnnotationMatch(
                            gold[gold_index].annotation_id,
                            generated_item.annotation_id,
                            edge_weight,
                        ),
                        *remaining_matches,
                    ),
                    key=lambda item: (item.gold_id, item.generated_id),
                )
            )
            candidate_weight = edge_weight + remaining_weight
            if candidate_weight > best_weight or (
                candidate_weight == best_weight
                and _edge_sequence(candidate_matches) < _edge_sequence(best_matches)
            ):
                best_weight, best_matches = candidate_weight, candidate_matches
        return best_weight, best_matches

    return choose(0, 0)[1]


def _severity_compatible(left: int | None, right: int | None) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(left - right) <= 1


def _edge_sequence(matches: Iterable[AnnotationMatch]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((match.gold_id, match.generated_id) for match in matches))


def _claim_anchors(value: Mapping[str, object]) -> tuple[str, ...]:
    raw = value.get("anchor_ids", value.get("anchors"))
    anchors = list(_strings(raw)) if raw is not None else []
    for key in ("anchor_id", "anchor"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            anchors.append(candidate.strip())
    normalized = tuple(sorted(set(anchors)))
    if not normalized:
        raise AnnotationValidationError("every dossier claim requires a stable anchor")
    return normalized


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        if value in (None, (), []):
            return ()
        raise AnnotationValidationError("expected a list of strings")
    return tuple(sorted({item.strip() for item in value if item.strip()}))


def _required_string(
    value: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) and fallback is not None:
        candidate = value.get(fallback)
    if not isinstance(candidate, str) or not candidate.strip():
        raise AnnotationValidationError(f"{key} is required")
    return candidate.strip()


def _first_string(value: Mapping[str, object], keys: Sequence[str]) -> str:
    for key in keys:
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return " ".join(candidate.split())
    raise AnnotationValidationError(f"one of {list(keys)} is required")


def _scope(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    if isinstance(value, list) and value and all(isinstance(item, str) for item in value):
        return "|".join(sorted({item.strip() for item in value if item.strip()}))
    raise AnnotationValidationError("claim scope must be a string or nonempty string list")


def _boolean(value: Mapping[str, object], key: str, default: bool) -> bool:
    candidate = value.get(key, default)
    if not isinstance(candidate, bool):
        raise AnnotationValidationError(f"{key} must be boolean")
    return candidate
