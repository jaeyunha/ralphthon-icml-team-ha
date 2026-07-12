"""Small RFC 8785 (JCS) encoder for JSON values accepted by the event authority."""

from __future__ import annotations

import math
from typing import Any


class CanonicalJsonError(ValueError):
    """Raised when a value is outside the interoperable JSON/JCS subset."""


def canonicalize(value: Any) -> str:
    """Return RFC 8785 canonical JSON for supported JSON values.

    Objects are sorted by their UTF-16 property-name representation as required
    by ECMAScript's JSON serialization. Numbers are restricted to finite IEEE
    754 values and interoperable integers (the JCS/I-JSON range).
    """
    return _encode(value)


def canonicalize_bytes(value: Any) -> bytes:
    return canonicalize(value).encode("utf-8")


def _encode(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, int):
        if not -(2**53 - 1) <= value <= 2**53 - 1:
            raise CanonicalJsonError("integer is outside the interoperable IEEE-754 range")
        return str(value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, list):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    if isinstance(value, dict):
        encoded: list[tuple[bytes, str]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalJsonError("JSON object keys must be strings")
            encoded.append(
                (key.encode("utf-16be", "surrogatepass"), _quote(key) + ":" + _encode(item))
            )
        encoded.sort(key=lambda pair: pair[0])
        return "{" + ",".join(item for _, item in encoded) + "}"
    raise CanonicalJsonError(f"unsupported JSON value: {type(value).__name__}")


def _quote(value: str) -> str:
    parts = ['"']
    for character in value:
        code = ord(character)
        if character == '"':
            parts.append('\\"')
        elif character == "\\":
            parts.append("\\\\")
        elif character == "\b":
            parts.append("\\b")
        elif character == "\f":
            parts.append("\\f")
        elif character == "\n":
            parts.append("\\n")
        elif character == "\r":
            parts.append("\\r")
        elif character == "\t":
            parts.append("\\t")
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        elif 0xD800 <= code <= 0xDFFF:
            raise CanonicalJsonError("strings must not contain unpaired UTF-16 surrogates")
        else:
            parts.append(character)
    parts.append('"')
    return "".join(parts)


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise CanonicalJsonError("JSON numbers must be finite")
    if value == 0:
        return "0"

    # CPython's repr is the correctly rounded shortest IEEE-754 decimal.  JCS
    # uses ECMAScript spelling, so only its fixed/scientific cutover and
    # exponent spelling need adjustment.
    text = repr(value).lower()
    negative = text.startswith("-")
    if negative:
        text = text[1:]
    if "e" in text:
        coefficient, exponent_text = text.split("e", 1)
        exponent = int(exponent_text)
    else:
        coefficient, exponent = text, 0
    if "." in coefficient:
        whole, fraction = coefficient.split(".", 1)
        digits = whole + fraction
        decimal_index = len(whole) + exponent
    else:
        digits = coefficient
        decimal_index = len(digits) + exponent
    digits = digits.lstrip("0").rstrip("0")
    assert digits

    absolute = abs(value)
    sign = "-" if negative else ""
    if 1e-6 <= absolute < 1e21:
        if decimal_index <= 0:
            return sign + "0." + "0" * (-decimal_index) + digits
        if decimal_index >= len(digits):
            return sign + digits + "0" * (decimal_index - len(digits))
        return sign + digits[:decimal_index] + "." + digits[decimal_index:]

    scientific_exponent = decimal_index - 1
    mantissa = digits[0] if len(digits) == 1 else digits[0] + "." + digits[1:]
    return (
        sign + mantissa + "e" + ("+" if scientific_exponent >= 0 else "") + str(scientific_exponent)
    )
