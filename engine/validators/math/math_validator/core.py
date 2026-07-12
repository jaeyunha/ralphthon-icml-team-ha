from __future__ import annotations

import ast
import hashlib
import itertools
import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import mpmath as mp

import sympy as sp
import z3
from jsonschema import Draft202012Validator

MATH_STATUSES = {
    "verified_formally",
    "verified_symbolically",
    "verified_exactly",
    "supported_numerically",
    "counterexample_found",
    "missing_assumption",
    "statement_mismatch",
    "equation_code_mismatch",
    "partially_verified",
    "inconclusive",
    "tool_unsupported",
}
NEGATIVE_STATUSES = {
    "counterexample_found",
    "missing_assumption",
    "statement_mismatch",
    "equation_code_mismatch",
}
MATH_VALIDATOR_TYPES = {"formal_math", "symbolic_math", "exact_math", "numerical_math"}
SEVERITIES = {"none", "minor", "major", "critical"}


class MathValidationError(RuntimeError):
    """Raised when a mathematical validation gate cannot be satisfied."""


@dataclass(frozen=True)
class Finding:
    finding_id: str
    validator_type: str
    claim_id: str | None
    status: str
    severity_candidate: str
    paper_anchors: tuple[str, ...]
    method: str
    observation: str
    limitations: str
    confirmation_paths: tuple[str, ...] = ()
    confidence: float = 0.0
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise MathValidationError("finding_id is required")
        if self.validator_type not in MATH_VALIDATOR_TYPES:
            raise MathValidationError(f"Unsupported math validator type: {self.validator_type}")
        if self.status not in MATH_STATUSES:
            raise MathValidationError(f"Unsupported mathematical status: {self.status}")
        if self.severity_candidate not in SEVERITIES:
            raise MathValidationError(f"Unsupported severity: {self.severity_candidate}")
        if not self.paper_anchors:
            raise MathValidationError("At least one paper anchor is required")
        if not 0 <= self.confidence <= 1:
            raise MathValidationError("confidence must be in [0, 1]")
        if (
            self.status in NEGATIVE_STATUSES
            and self.severity_candidate in {"major", "critical"}
            and not self.confirmation_paths
        ):
            raise MathValidationError(
                "High-impact negative findings require an independent confirmation path"
            )

    def as_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "finding_id": self.finding_id,
            "validator_type": self.validator_type,
            "claim_id": self.claim_id,
            "status": self.status,
            "severity_candidate": self.severity_candidate,
            "paper_anchors": list(self.paper_anchors),
            "method": self.method,
            "observation": self.observation,
            "limitations": self.limitations,
            "confirmation_paths": list(self.confirmation_paths),
            "confidence": self.confidence,
        }
        if self.artifact_refs:
            value["artifact_refs"] = list(self.artifact_refs)
        return value


def validate_finding(finding: Finding | dict[str, Any], schema_path: Path) -> None:
    value = finding.as_dict() if isinstance(finding, Finding) else finding
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_symbols(names: list[str]) -> dict[str, sp.Symbol]:
    return {name: sp.Symbol(name, real=True) for name in names}


def parse_expression(expression: str, symbols: dict[str, sp.Symbol]) -> sp.Expr:
    allowed: dict[str, Any] = {
        **symbols,
        "Abs": sp.Abs,
        "exp": sp.exp,
        "log": sp.log,
        "sin": sp.sin,
        "cos": sp.cos,
        "sqrt": sp.sqrt,
        "pi": sp.pi,
        "Matrix": sp.Matrix,
    }
    try:
        return sp.sympify(expression, locals=allowed, evaluate=True)
    except (sp.SympifyError, TypeError, ValueError) as exc:
        raise MathValidationError(f"Invalid symbolic expression: {expression}") from exc


def check_symbolic_identity(job: dict[str, Any]) -> dict[str, Any]:
    symbols = parse_symbols(list(job.get("variables", [])))
    left = parse_expression(str(job["left"]), symbols)
    right = parse_expression(str(job["right"]), symbols)
    difference = sp.simplify(left - right)
    equivalent = bool(difference == 0)
    return {
        "equivalent": equivalent,
        "left": str(left),
        "right": str(right),
        "simplified_difference": str(difference),
        "tool": f"sympy-{sp.__version__}",
    }


def check_gradient(job: dict[str, Any]) -> dict[str, Any]:
    variable_names = list(job["variables"])
    symbols = parse_symbols(variable_names)
    expression = parse_expression(str(job["expression"]), symbols)
    expected = [parse_expression(str(item), symbols) for item in job["expected_gradient"]]
    actual = [sp.diff(expression, symbols[name]) for name in variable_names]
    differences = [sp.simplify(a - b) for a, b in zip(actual, expected, strict=True)]
    return {
        "equivalent": all(item == 0 for item in differences),
        "actual_gradient": [str(item) for item in actual],
        "expected_gradient": [str(item) for item in expected],
        "simplified_differences": [str(item) for item in differences],
        "tool": f"sympy-{sp.__version__}",
    }


class _Z3Translator(ast.NodeVisitor):
    def __init__(self, variables: dict[str, Any]) -> None:
        self.variables = variables

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id not in self.variables:
            raise MathValidationError(f"Undeclared SMT variable: {node.id}")
        return self.variables[node.id]

    def visit_Constant(self, node: ast.Constant) -> Any:
        if isinstance(node.value, (bool, int, float)):
            return node.value
        raise MathValidationError("Unsupported SMT constant")

    def visit_UnaryOp(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        if isinstance(node.op, ast.Not):
            return z3.Not(operand)
        if isinstance(node.op, ast.USub):
            return -operand
        raise MathValidationError("Unsupported SMT unary operator")

    def visit_BoolOp(self, node: ast.BoolOp) -> Any:
        values = [self.visit(item) for item in node.values]
        if isinstance(node.op, ast.And):
            return z3.And(*values)
        if isinstance(node.op, ast.Or):
            return z3.Or(*values)
        raise MathValidationError("Unsupported SMT boolean operator")

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        left, right = self.visit(node.left), self.visit(node.right)
        operations = {
            ast.Add: lambda: left + right,
            ast.Sub: lambda: left - right,
            ast.Mult: lambda: left * right,
            ast.Div: lambda: left / right,
            ast.Mod: lambda: left % right,
            ast.Pow: lambda: left**right,
        }
        for operation, callback in operations.items():
            if isinstance(node.op, operation):
                return callback()
        raise MathValidationError("Unsupported SMT arithmetic operator")

    def visit_Compare(self, node: ast.Compare) -> Any:
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise MathValidationError("Chained SMT comparisons are not supported")
        left, right = self.visit(node.left), self.visit(node.comparators[0])
        op = node.ops[0]
        if isinstance(op, ast.Eq):
            return left == right
        if isinstance(op, ast.NotEq):
            return left != right
        if isinstance(op, ast.Lt):
            return left < right
        if isinstance(op, ast.LtE):
            return left <= right
        if isinstance(op, ast.Gt):
            return left > right
        if isinstance(op, ast.GtE):
            return left >= right
        raise MathValidationError("Unsupported SMT comparison")

    def generic_visit(self, node: ast.AST) -> Any:
        raise MathValidationError(f"Unsupported SMT syntax: {node.__class__.__name__}")


def _z3_expression(expression: str, variables: dict[str, Any]) -> Any:
    return _Z3Translator(variables).visit(ast.parse(expression, mode="eval").body)


def check_smt_implication(job: dict[str, Any]) -> dict[str, Any]:
    variables: dict[str, Any] = {}
    for name, kind in dict(job["variables"]).items():
        variables[name] = z3.Int(name) if kind == "int" else z3.Real(name)
    solver = z3.Solver()
    for constraint in job.get("constraints", []):
        solver.add(_z3_expression(str(constraint), variables))
    solver.add(z3.Not(_z3_expression(str(job["conclusion"]), variables)))
    result = solver.check()
    model: dict[str, str] = {}
    if result == z3.sat:
        candidate = solver.model()
        model = {
            name: str(candidate.eval(value, model_completion=True))
            for name, value in variables.items()
        }
    return {
        "result": str(result),
        "counterexample": model or None,
        "tool": f"z3-{z3.get_version_string()}",
    }


def _fraction_range(spec: dict[str, Any]) -> list[Fraction]:
    low = Fraction(str(spec["min"]))
    high = Fraction(str(spec["max"]))
    points = int(spec.get("points", 9))
    if points < 2:
        return [low]
    step = (high - low) / (points - 1)
    values = [low + index * step for index in range(points)]
    for boundary in (low, high, Fraction(0), Fraction(1), Fraction(-1)):
        if low <= boundary <= high and boundary not in values:
            values.append(boundary)
    return sorted(values)


def check_numerical_property(job: dict[str, Any]) -> dict[str, Any]:
    variable_specs = dict(job["variables"])
    symbols = parse_symbols(list(variable_specs))
    left = parse_expression(str(job["left"]), symbols)
    right = parse_expression(str(job["right"]), symbols)
    relation = str(job.get("relation", "=="))
    tolerance = float(job.get("tolerance", 1e-12))
    residual = sp.simplify(left - right)
    interval_function = sp.lambdify(list(symbols.values()), residual, modules="mpmath")
    interval_inputs = [
        mp.iv.mpf([str(variable_specs[name]["min"]), str(variable_specs[name]["max"])])
        for name in symbols
    ]
    try:
        interval_residual = str(interval_function(*interval_inputs))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        interval_residual = f"unsupported:{exc.__class__.__name__}"
    methods = [
        "exact-rational-grid",
        "80-digit-evaluation",
        "interval-arithmetic-enclosure",
        "deterministic-property-sweep",
        "exhaustive-small-cases",
        "boundary-and-adversarial-points",
    ]
    samples = 0
    for values in itertools.product(*[_fraction_range(variable_specs[name]) for name in symbols]):
        substitution = {
            symbols[name]: sp.Rational(value.numerator, value.denominator)
            for name, value in zip(symbols, values, strict=True)
        }
        left_value = sp.N(left.subs(substitution), 80)
        right_value = sp.N(right.subs(substitution), 80)
        samples += 1
        if relation == "==":
            satisfied = abs(float(left_value - right_value)) <= tolerance
        elif relation == "<=":
            satisfied = float(left_value - right_value) <= tolerance
        elif relation == ">=":
            satisfied = float(right_value - left_value) <= tolerance
        elif relation == "<":
            satisfied = float(left_value) < float(right_value)
        elif relation == ">":
            satisfied = float(left_value) > float(right_value)
        else:
            raise MathValidationError(f"Unsupported numerical relation: {relation}")
        if not satisfied:
            return {
                "counterexample": {
                    name: str(value) for name, value in zip(symbols, values, strict=True)
                },
                "left_value": str(left_value),
                "right_value": str(right_value),
                "samples_checked": samples,
                "interval_residual": interval_residual,
                "methods": methods,
            }
    return {
        "counterexample": None,
        "samples_checked": samples,
        "interval_residual": interval_residual,
        "methods": methods,
    }


def check_shapes(job: dict[str, Any]) -> dict[str, Any]:
    shapes = {name: tuple(value) for name, value in dict(job["shapes"]).items()}
    errors: list[str] = []
    inferred = dict(shapes)
    for operation in job.get("operations", []):
        kind = operation["op"]
        if kind == "matmul":
            left, right = inferred[operation["left"]], inferred[operation["right"]]
            if len(left) != 2 or len(right) != 2 or left[1] != right[0]:
                errors.append(f"matmul mismatch {left} x {right}")
                continue
            inferred[operation["out"]] = (left[0], right[1])
        elif kind == "add":
            left, right = inferred[operation["left"]], inferred[operation["right"]]
            if left != right:
                errors.append(f"add mismatch {left} + {right}")
                continue
            inferred[operation["out"]] = left
        elif kind == "sum":
            source = inferred[operation["source"]]
            axis = int(operation["axis"])
            if axis < 0 or axis >= len(source):
                errors.append(f"invalid sum axis {axis} for {source}")
                continue
            inferred[operation["out"]] = source[:axis] + source[axis + 1 :]
        else:
            raise MathValidationError(f"Unsupported shape operation: {kind}")
    expected = job.get("expected")
    if expected is not None and tuple(expected) != inferred.get(job.get("output")):
        errors.append(f"expected {tuple(expected)}, inferred {inferred.get(job.get('output'))}")
    return {
        "valid": not errors,
        "inferred_shapes": {key: list(value) for key, value in inferred.items()},
        "errors": errors,
    }


def check_equation_to_code(job: dict[str, Any]) -> dict[str, Any]:
    conformance = job.get("g1_conformance")
    source = dict(conformance) if isinstance(conformance, dict) else job
    variables = list(source["variables"])
    equation_expression = str(source.get("paper_expression", source.get("equation_expression", "")))
    implementation_expression = str(source["implementation_expression"])
    symbols = parse_symbols(variables)
    equation = parse_expression(equation_expression, symbols)
    implementation = parse_expression(implementation_expression, symbols)
    difference = sp.simplify(equation - implementation)
    provenance = source.get("artifact_ref")
    if difference == 0:
        return {
            "conformant": True,
            "simplified_difference": "0",
            "counterexample": None,
            "g1_artifact_ref": provenance,
        }
    numerical = check_numerical_property(
        {
            "variables": source["sample_domains"],
            "left": equation_expression,
            "right": implementation_expression,
            "relation": "==",
            "tolerance": source.get("tolerance", 1e-12),
        }
    )
    return {
        "conformant": numerical["counterexample"] is None,
        "simplified_difference": str(difference),
        "counterexample": numerical["counterexample"],
        "samples_checked": numerical["samples_checked"],
        "interval_residual": numerical["interval_residual"],
        "g1_artifact_ref": provenance,
    }


def check_assumptions(job: dict[str, Any], statement: str) -> dict[str, Any]:
    lowered = statement.lower()
    missing = [
        phrase for phrase in job.get("required_phrases", []) if phrase.lower() not in lowered
    ]
    undefined = [symbol for symbol in job.get("symbols", []) if symbol not in statement]
    return {
        "missing_required_phrases": missing,
        "undefined_symbols": undefined,
        "complete": not missing and not undefined,
    }


def dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
