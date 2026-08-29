"""Shared command-line contracts for x-npi JSON examples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, IO, Tuple

from .jsonio import error, ok, print_json
from .protocol import ProtocolAnalysisError
from .wave import SignalPreflightError


Json = Dict[str, Any]


def sampling_contract(cfg: Json) -> Tuple[str, str | None]:
    legacy = [key for key in ("clock_edge", "posedge") if key in cfg]
    if legacy:
        raise ValueError(f"legacy sampling fields are not supported: {', '.join(legacy)}; use edge and sample_point")
    edge = str(cfg.get("edge", "negedge")).lower()
    sample_point = cfg.get("sample_point")
    if edge not in {"negedge", "posedge"}:
        raise ValueError("edge must be negedge or posedge")
    if edge == "posedge" and sample_point not in {"before", "after"}:
        raise ValueError("posedge requires sample_point=before or after")
    if edge == "negedge" and sample_point is not None:
        raise ValueError("sample_point is only valid with edge=posedge")
    return edge, sample_point


def require_output(detail: str, output: str | None) -> None:
    if detail != "summary" and not output:
        raise ValueError("--output is required when --detail is transactions, timeline, or full")


def emit_result(action: str, result: Json, detail: str, output: str | None,
                json_stream: IO[str]) -> None:
    meta = dict(result.get("meta", {}))
    if detail == "summary":
        print_json(ok(action, summary=result["summary"], meta=meta), json_stream)
        return
    assert output is not None
    output_path = Path(output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    document = ok(action, data=result.get("data", {}), summary=result["summary"], meta=meta)
    output_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    meta["output"] = str(output_path)
    meta["detail"] = detail
    print_json(ok(action, summary=result["summary"], meta=meta), json_stream)


def error_document(action: str, exc: Exception, *, scan_meta: Json | None = None) -> Json:
    if isinstance(exc, ProtocolAnalysisError):
        fields = exc.as_dict()
        code = str(fields.pop("code"))
        message = str(fields.pop("message"))
        if scan_meta:
            fields["scan"] = scan_meta
        return error(action, code, message, **fields)
    if isinstance(exc, SignalPreflightError):
        return error(action, "SIGNAL_PREFLIGHT_FAILED", str(exc), stage="preflight", missing=exc.missing)
    if isinstance(exc, (ValueError, KeyError, json.JSONDecodeError)):
        return error(action, "CONFIG_INVALID", str(exc), stage="config")
    return error(action, "FAILED", str(exc))
