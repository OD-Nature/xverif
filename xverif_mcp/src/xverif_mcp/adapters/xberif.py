"""Stateless xberif adapter - project context / summary cards."""
from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from xverif_mcp.config import enable_write
from xverif_mcp.errors import error_payload, write_disabled
from xverif_mcp.import_paths import ensure_tool_import_paths

ensure_tool_import_paths()


@dataclass(frozen=True)
class _XberifApi:
    repair_catalog: Any
    validate_all: Any
    init_config: Any
    initialize: Any
    brief: Any
    brief_result: Any
    get_topic: Any
    get_topic_detail: Any
    list_topics: Any
    status: Any
    render_list_topics: Any
    render_repair: Any
    render_status: Any
    render_topic: Any


def _load_xberif() -> _XberifApi:
    try:
        from xberif.cards import repair_catalog, validate_all
        from xberif.config import init_config
        from xberif.init_flow import initialize
        from xberif.query import (brief, brief_result, get_topic, get_topic_detail,
                                  list_topics, status)
        from xberif.xout import (render_list_topics, render_repair, render_status,
                                  render_topic)
    except ModuleNotFoundError as exc:
        missing = exc.name or str(exc)
        raise RuntimeError(
            f"xberif dependency is not available in this Python environment: {missing}"
        ) from exc
    return _XberifApi(
        repair_catalog=repair_catalog,
        validate_all=validate_all,
        init_config=init_config,
        initialize=initialize,
        brief=brief,
        brief_result=brief_result,
        get_topic=get_topic,
        get_topic_detail=get_topic_detail,
        list_topics=list_topics,
        status=status,
        render_list_topics=render_list_topics,
        render_repair=render_repair,
        render_status=render_status,
        render_topic=render_topic,
    )


def _root(project_root: Optional[str]) -> Path:
    return Path(project_root or os.getcwd()).resolve()


def _error(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    if code and message:
        return error_payload(str(code), str(message))
    return error_payload("XBERIF_ERROR", str(exc))


def _next_action_for_state(state: str) -> str:
    if state == "not_configured":
        return "run xberif config init --kind <bt|it|st|soc>"
    if state == "configured_only":
        return "run xberif init --model <model>"
    if state == "generated_raw":
        return "run xberif repair-catalog"
    if state == "invalid":
        return "run xberif validate and fix reported cards/details"
    return "use xberif brief/get/detail"


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _status_fallback(root: Path) -> dict:
    cfg_path = root / "xberif" / "kind.toml"
    topics_path = root / "xberif" / "topics.toml"
    sdir = root / ".xberif"
    catalog_path = sdir / "cards.json"
    raw_cards = sorted((sdir / "cards").glob("*.json")) if (sdir / "cards").is_dir() else []
    raw_details = sorted((sdir / "details").glob("*.md")) if (sdir / "details").is_dir() else []
    if not cfg_path.exists() or not topics_path.exists():
        state = "not_configured"
    elif not sdir.exists():
        state = "configured_only"
    else:
        catalog_count = 0
        if catalog_path.exists():
            try:
                catalog_count = len(_read_json(catalog_path).get("cards", []))
            except Exception:
                catalog_count = 0
        if catalog_count > 0:
            state = "ready"
        elif raw_cards or raw_details:
            state = "generated_raw"
        else:
            state = "configured_only"
    return {
        "schema_version": "xberif.status.v1",
        "state": state,
        "configured": cfg_path.exists() and topics_path.exists(),
        "state_dir_exists": sdir.exists(),
        "catalog_exists": catalog_path.exists(),
        "catalog_card_count": len(_read_json(catalog_path).get("cards", [])) if catalog_path.exists() else 0,
        "raw_card_count": len(raw_cards),
        "raw_detail_count": len(raw_details),
        "next_action": _next_action_for_state(state),
    }


def _render_status_fallback(payload: dict) -> str:
    lines = [
        "@xberif.status.v1",
        "summary:",
        f"  state: {payload.get('state')}",
        f"  configured: {str(payload.get('configured')).lower()}",
        f"  state_dir_exists: {str(payload.get('state_dir_exists')).lower()}",
        f"  catalog_exists: {str(payload.get('catalog_exists')).lower()}",
        f"  catalog_card_count: {payload.get('catalog_card_count')}",
        f"  raw_card_count: {payload.get('raw_card_count')}",
        f"  raw_detail_count: {payload.get('raw_detail_count')}",
        "",
        "next:",
        f"  {payload.get('next_action')}",
    ]
    return "\n".join(lines).rstrip() + "\n"


def context_status(project_root: Optional[str] = None,
                   output_format: str = "json") -> Any:
    """Check xberif project status."""
    root = _root(project_root)
    try:
        api = _load_xberif()
        payload = api.status(root)
    except RuntimeError:
        payload = _status_fallback(root)
        if output_format == "json":
            return payload
        return _render_status_fallback(payload)
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return api.render_status(payload)


def context_list_topics(project_root: Optional[str] = None,
                        output_format: str = "json") -> Any:
    """List all known context topics."""
    try:
        api = _load_xberif()
        payload = api.list_topics(_root(project_root))
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return api.render_list_topics(payload)


def context_brief(mode: str = "debug", project_root: Optional[str] = None,
                  output_format: str = "xout") -> Any:
    """Generate a context brief (summary) for the given mode."""
    root = _root(project_root)
    try:
        api = _load_xberif()
        if output_format == "json":
            return api.brief_result(root, mode)
        return api.brief(root, mode)
    except Exception as exc:
        return _error(exc)


def context_get(topic: str, detail: bool = False,
                project_root: Optional[str] = None,
                output_format: str = "xout") -> Any:
    """Get a topic card (optionally with detail content)."""
    root = _root(project_root)
    try:
        api = _load_xberif()
        if detail:
            detail_payload = api.get_topic_detail(root, topic)
            if output_format == "json":
                return detail_payload
            return detail_payload["content"]
        payload = api.get_topic(root, topic)
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return api.render_topic(payload)


def context_detail(topic: str, project_root: Optional[str] = None,
                   output_format: str = "markdown") -> Any:
    """Get the full detail markdown for a topic."""
    try:
        api = _load_xberif()
        payload = api.get_topic_detail(_root(project_root), topic)
    except Exception as exc:
        return _error(exc)
    if output_format == "json":
        return payload
    return payload["content"]


def context_validate(project_root: Optional[str] = None,
                     output_format: str = "json") -> Any:
    """Validate project cards and detail files."""
    try:
        api = _load_xberif()
        errors = api.validate_all(_root(project_root))
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
        api = _load_xberif()
        files = api.init_config(_root(project_root), kind)
        return {"ok": True, "files": [str(path) for path in files]}
    except Exception as exc:
        return _error(exc)


def context_init(model: str, project_root: Optional[str] = None) -> Any:
    """Initialize xberif project structure with an external agent model."""
    if not enable_write():
        return write_disabled("context_init")
    try:
        api = _load_xberif()
        api.initialize(_root(project_root), model)
        return {"ok": True}
    except Exception as exc:
        return _error(exc)


def context_repair(project_root: Optional[str] = None) -> Any:
    """Repair xberif catalog index."""
    if not enable_write():
        return write_disabled("context_repair")
    try:
        api = _load_xberif()
        catalog = api.repair_catalog(_root(project_root))
        payload = {"ok": True, "catalog_card_count": len(catalog.get("cards", []))}
        payload["catalog"] = catalog
        return payload
    except Exception as exc:
        return _error(exc)
