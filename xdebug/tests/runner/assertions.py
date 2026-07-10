from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Sequence


class InvariantError(AssertionError):
    pass


_MISSING = object()
_ABSENT = object()


def get_path(value: Any, path: str, default: Any = _MISSING) -> Any:
    current = value
    if not path:
        return current
    for part in path.split("."):
        if isinstance(current, Mapping) and part in current:
            current = current[part]
            continue
        if isinstance(current, Sequence) and not isinstance(current, (str, bytes)):
            try:
                current = current[int(part)]
                continue
            except (ValueError, IndexError):
                pass
        if default is _MISSING:
            raise InvariantError("missing response path: %s" % path)
        return default
    return current


def _assert_non_empty(value: Any, path: str) -> None:
    if value is None or value == "" or value == [] or value == {}:
        raise InvariantError("response path is empty: %s" % path)


def _contains(container: Any, expected: Any) -> bool:
    if isinstance(container, str):
        return str(expected) in container
    if isinstance(container, Mapping):
        return expected in container
    if isinstance(container, Iterable):
        return expected in container
    return False


def assert_invariants(response: Any, expected: Mapping[str, Any]) -> None:
    if not isinstance(response, Mapping):
        raise InvariantError("response must be an object")

    if "ok" in expected and bool(response.get("ok")) != bool(expected["ok"]):
        raise InvariantError(
            "ok mismatch: actual=%r expected=%r"
            % (response.get("ok"), expected["ok"])
        )

    if "error_code" in expected:
        actual = get_path(response, "error.code")
        if actual != expected["error_code"]:
            raise InvariantError(
                "error.code mismatch: actual=%r expected=%r"
                % (actual, expected["error_code"])
            )

    for path in expected.get("required_paths", []):
        get_path(response, path)

    for path in expected.get("absent_paths", []):
        if get_path(response, path, default=_ABSENT) is not _ABSENT:
            raise InvariantError("response path must be absent: %s" % path)

    for path in expected.get("non_empty", []):
        _assert_non_empty(get_path(response, path), path)

    for path, value in expected.get("equals", {}).items():
        actual = get_path(response, path)
        if actual != value:
            raise InvariantError(
                "%s mismatch: actual=%r expected=%r" % (path, actual, value)
            )

    for path, value in expected.get("min", {}).items():
        actual = get_path(response, path)
        if actual < value:
            raise InvariantError(
                "%s below minimum: actual=%r minimum=%r" % (path, actual, value)
            )

    for path, value in expected.get("max", {}).items():
        actual = get_path(response, path)
        if actual > value:
            raise InvariantError(
                "%s above maximum: actual=%r maximum=%r" % (path, actual, value)
            )

    for path, values in expected.get("contains", {}).items():
        actual = get_path(response, path)
        for value in values if isinstance(values, list) else [values]:
            if not _contains(actual, value):
                raise InvariantError(
                    "%s does not contain %r: actual=%r" % (path, value, actual)
                )

    for path, values in expected.get("allowed_values", {}).items():
        actual = get_path(response, path)
        if actual not in values:
            raise InvariantError(
                "%s is not allowed: actual=%r allowed=%r"
                % (path, actual, values)
            )
