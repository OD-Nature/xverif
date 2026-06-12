"""Stateless xsva adapter — SVA semantic analysis.

xsva requires a SVA source file path (--file). It does NOT support JSON-on-stdin.
"""
from __future__ import annotations

from typing import Any, Optional

from xverif_mcp.runner import StatelessCliRunner

runner = StatelessCliRunner()


def sva_list(file: str, output_format: str = "json") -> Any:
    """List all property/assertion names in a SVA source file."""
    text = runner.run_text("xsva", ["list", "--file", file])
    return text  # xsva list 不支持 --json，始终返回文本


def sva_scan(file: str, output_format: str = "json") -> Any:
    """Scan syntax constructs in a SVA source file."""
    return runner.run_text("xsva", ["scan", "--file", file])  # 不支持 --json


def sva_parse(file: str, property: str, emit: str = "timeline-ir",
              output_format: str = "json") -> Any:
    """Parse a SVA property into IR (surface-ir/sequence-ir/timeline-ir)."""
    argv = ["parse", "--file", file, "--property", property, "--emit", emit]
    return runner.run_json("xsva", argv)


def sva_explain(file: str, property: str, strict: bool = False,
                output_format: str = "xout") -> Any:
    """Generate a human-readable explanation of a SVA property."""
    argv = ["explain", "--file", file, "--property", property]
    if output_format in ("json", "markdown"):
        argv.append(f"--{output_format}")
    if strict:
        argv.append("--strict")
    if output_format == "json":
        return runner.run_json("xsva", argv)
    return runner.run_text("xsva", argv)
