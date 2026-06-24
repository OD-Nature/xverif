"""Stateless xberif adapter - project context / summary cards."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from xverif_mcp.config import enable_write
from xverif_mcp.errors import error_payload, write_disabled
from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()

from xberif.cards import repair_catalog, validate_all
from xberif.config import init_config
from xberif.errors import XberifError
from xberif.init_flow import initialize
from xberif.query import (brief, brief_result, get_topic, get_topic_detail,
                          list_topics, status)
from xberif.xout import render_list_topics, render_repair, render_status, render_topic


def _root(project_root: Optional[str]) -> Path:
    return Path(project_root or os.getcwd()).resolve()


def _error(exc: Exception) -> dict:
    if isinstance(exc, XberifError):
        return error_payload(exc.code, exc.message)
    return error_payload("XBERIF_ERROR", str(exc))


def context_status(project_root: Optional[str] = None,
                   output_format: str = "json") -> Any:
    """Check xberif project status."""
    try:
        payload = status(_root(project_root))
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return render_status(payload)


def context_list_topics(project_root: Optional[str] = None,
                        output_format: str = "json") -> Any:
    """List all known context topics."""
    try:
        payload = list_topics(_root(project_root))
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return render_list_topics(payload)


def context_brief(mode: str = "debug", project_root: Optional[str] = None,
                  output_format: str = "xout") -> Any:
    """Generate a context brief (summary) for the given mode."""
    root = _root(project_root)
    try:
        if output_format == "json":
            return brief_result(root, mode)
        return brief(root, mode)
    except Exception as exc:
        return _error(exc)


def context_get(topic: str, detail: bool = False,
                project_root: Optional[str] = None,
                output_format: str = "xout") -> Any:
    """Get a topic card (optionally with detail content)."""
    root = _root(project_root)
    try:
        if detail:
            detail_payload = get_topic_detail(root, topic)
            if output_format == "json":
                return detail_payload
            return detail_payload["content"]
        payload = get_topic(root, topic)
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return render_topic(payload)


def context_detail(topic: str, project_root: Optional[str] = None,
                   output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic."""
    try:
        payload = get_topic_detail(_root(project_root), topic)
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return payload["content"]


def context_validate(project_root: Optional[str] = None,
                     output_format: str = "json") -> Any:
    """Validate project cards and detail files."""
    try:
        errors = validate_all(_root(project_root))
    except Exception as exc:
        return _error(exc)
    payload = {"ok": not errors, "errors": errors}
    if output_format == "json":
        return payload
    return "ok\n" if not errors else "\n".join(f"error: {err}" for err in errors) + "\n"


def context_config_init(kind: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif kind.toml config for a project kind."""
    if not enable_write():
        return write_disabled("context_config_init")
    try:
        files = init_config(_root(project_root), kind)
        return {"ok": True, "files": [str(path) for path in files]}
    except Exception as exc:
        return _error(exc)


def context_init(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif project structure with an external agent model."""
    if not enable_write():
        return write_disabled("context_init")
    try:
        initialize(_root(project_root), model)
        return {"ok": True}
    except Exception as exc:
        return _error(exc)


def context_repair(project_root: Optional[str] = None) -> Any:
    """Repair xberif catalog index."""
    if not enable_write():
        return write_disabled("context_repair")
    try:
        catalog = repair_catalog(_root(project_root))
        payload = {"ok": True, "catalog_card_count": len(catalog.get("cards", []))}
        payload["catalog"] = catalog
        return payload
    except Exception as exc:
        return _error(exc)
