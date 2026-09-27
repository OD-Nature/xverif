"""Structured assertion and functional coverage gap artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List

from .errors import XcovError

Json = Dict[str, Any]


def build_gap_payload(metric: str, vdb: str, rows: Iterable[Json]) -> Json:
    prefix = "A" if metric == "assert" else "FC"
    leaf_type = "npiCovCoverBin" if metric == "functional" else None
    gaps: List[Json] = []
    for row in rows:
        if leaf_type and row.get("type") != leaf_type:
            continue
        if int(row.get("coverable") or 0) <= int(row.get("covered") or 0):
            continue
        gaps.append({
            "gap_id": f"{prefix}{len(gaps) + 1:04d}",
            "scope": row.get("scope"),
            "kind": row.get("type"),
            "name": row.get("name"),
            "full_name": row.get("full_name"),
            "covergroup": row.get("covergroup"),
            "coverpoint": row.get("coverpoint"),
            "cross": row.get("cross"),
            "bin": row.get("bin"),
            "covered": row.get("covered"),
            "coverable": row.get("coverable"),
            "count": row.get("count"),
            "evidence": row.get("evidence") or {},
        })
    source_files = sorted({
        str((gap.get("evidence") or {}).get("file"))
        for gap in gaps if (gap.get("evidence") or {}).get("file")
    })
    return {
        "artifact_format": f"xcov_{metric}_gaps.v1",
        "metric": metric,
        "exclusion_locator": {
            "version": "xcov.urg_semantic.v1",
            "vdb": str(Path(vdb).resolve()),
        },
        "source_files": source_files,
        "gap_count": len(gaps),
        "gaps": gaps,
    }


def parse_urg_gap_report(
    metric: str, report_path: str | Path, *, variable_report_path: str | Path | None = None,
) -> List[Json]:
    """Parse URG text detail without importing or invoking pynpi."""
    path = Path(report_path)
    text = path.read_text(encoding="utf-8", errors="strict")
    if metric == "assert":
        return _parse_assert_gaps(text)
    if metric == "functional":
        rows = _parse_functional_gaps(text)
        if variable_report_path is not None:
            variables = _parse_functional_gaps(
                Path(variable_report_path).read_text(encoding="utf-8", errors="strict"),
                variables_only=True,
            )
            def totals(items):
                result = {}
                for row in items:
                    if row.get("coverpoint"):
                        key = (row.get("scope"), row.get("covergroup"), row["coverpoint"])
                        result[key] = result.get(key, 0) + row["coverable"]
                return result
            if totals(variables) != totals(rows):
                raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional variable views disagree", metric="functional")
            rows = variables + [row for row in rows if row.get("cross")]
        return rows
    raise ValueError(f"unsupported URG gap metric: {metric}")


def _parse_assert_gaps(text: str) -> List[Json]:
    rows: List[Json] = []
    sections = (
        ("Assertions", "npiCovAssert", 6),
        ("Cover Properties", "npiCovCoverProperty", 5),
        ("Cover Sequences", "npiCovCoverSequence", 5),
    )
    for category, kind, numeric_columns in sections:
        heading = category + " Uncovered:"
        category_rows: List[Json] = []
        start = text.find(heading)
        if start >= 0:
            body_start = start + len(heading)
            end_match = re.search(
                r"^(?:-{20,}|(?:Assertions|Cover Properties|Cover Sequences) [^\r\n:]+:)[ \t]*\r?$",
                text[body_start:], re.MULTILINE,
            )
            end = body_start + end_match.start() if end_match else len(text)
            for line in text[body_start:end].splitlines():
                # Split the numeric suffix, preserving spaces in escaped SV
                # names; hierarchy roots are design-specific, never fixed 'top'.
                fields = line.rsplit(None, numeric_columns)
                if len(fields) != numeric_columns + 1:
                    continue
                full_name, *numeric = fields
                full_name = full_name.strip()
                if not all(value.isdigit() for value in numeric):
                    continue
                if "." not in full_name:
                    raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "assertion scope is missing", metric="assert")
                scope, name = full_name.rsplit(".", 1)
                count = int(numeric[-3]) if kind == "npiCovAssert" else int(numeric[-2])
                category_rows.append({
                    "metric": "assert", "type": kind, "scope": scope,
                    "name": name, "full_name": full_name,
                    "covered": 0, "coverable": 1, "count": count, "evidence": {},
                })
        summary = re.search(
            rf"^Summary for {re.escape(category)}[ \t]*\r?$([\s\S]*?)(?=^-{{20,}}|\Z)",
            text, re.MULTILINE,
        )
        expected = re.search(r"^Uncovered[ \t]+(\d+)\b", summary.group(1), re.MULTILINE) if summary else None
        if expected and len(category_rows) != int(expected.group(1)):
            raise XcovError(
                "URG_DETAIL_PARSE_INCOMPLETE", "assertion gap count does not match URG summary",
                metric="assert", category=category,
                expected=int(expected.group(1)), parsed=len(category_rows),
            )
        rows.extend(category_rows)
    return rows


def _parse_functional_gaps(text: str, *, variables_only: bool = False) -> List[Json]:
    rows: List[Json] = []
    headers = list(re.finditer(
        r"^Group(?: Instance)? :\s*(\S.*?)\s*$",
        text,
        re.MULTILINE,
    ))
    for index, header in enumerate(headers):
        block_end = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        block = text[header.end():block_end]
        # Skip the short preamble before URG repeats the first real block.
        if "Summary for " not in block:
            continue
        identity = header.group(1).strip()
        group_match = re.search(r"(?:^|\s)(\S+::\S+_cg|\S+::\S+)\s*$", block, re.MULTILINE)
        covergroup = group_match.group(1) if group_match else identity
        scope = ".".join(covergroup.split("::")[:-1]) if "::" in covergroup else ""
        if "." in identity and "::" not in identity:
            scope = identity.rsplit(".", 1)[0]
        source_match = re.search(
            r"^Source File\(s\)\s*:\s*\n+(\S+)",
            block,
            re.MULTILINE,
        )
        evidence = {"file": source_match.group(1), "line": None} if source_match else {}
        summaries = list(re.finditer(
            r"^Summary for (Variable|Cross)\s+(\S+)\s*$",
            block,
            re.MULTILINE,
        ))
        for summary_index, summary in enumerate(summaries):
            section_end = (
                summaries[summary_index + 1].start()
                if summary_index + 1 < len(summaries) else len(block)
            )
            if variables_only and summary.group(1) != "Variable":
                continue
            section = block[summary.end():section_end]
            expected_rows = re.findall(
                r"^(?:User Defined|Automatically Generated)(?: Cross)? Bins[ \t]+\d+[ \t]+(\d+)\b",
                section, re.MULTILINE,
            )
            expected = sum(int(value) for value in expected_rows) if expected_rows else None
            marker = re.search(
                r"^(?:Uncovered bins|Decompressed uncovered bins for [^\r\n]+)[ \t]*\r?$",
                section, re.MULTILINE,
            )
            if not marker:
                if expected:
                    raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional gap table is missing", metric="functional", object=summary.group(2))
                continue
            lines = section[marker.end():].splitlines()
            table_header = next((pos for pos, line in enumerate(lines) if "COUNT" in line and "AT LEAST" in line), None)
            if table_header is None:
                raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional gap header is missing", metric="functional")
            expanded = "NUMBER" not in lines[table_header]
            numeric_columns = 2 if expanded else 3
            object_name = summary.group(2)
            object_rows = 0
            for line in lines[table_header + 1:]:
                stripped = line.strip()
                if not stripped:
                    continue
                if set(stripped) <= {"-", " "}:
                    break
                fields = stripped.split()
                bin_parts = fields[:-numeric_columns]
                bin_count = 1
                if (not expanded and variables_only and len(fields) > numeric_columns
                        and fields[-3:-1] == ["--", "--"] and fields[-1].isdigit()):
                    # Keep the exact URG/NPI auto-bin range as one actionable
                    # gap. Expanding it here would imply unsupported per-bin
                    # exclusion and could accidentally exclude its neighbours.
                    bin_name = " ".join(bin_parts)
                    span = re.fullmatch(r"\[auto\[(\d+)\] - auto\[(\d+)\]\]", bin_name)
                    bin_count = int(fields[-1])
                    if not span or bin_count != int(span[2]) - int(span[1]) + 1 or bin_count < 1:
                        raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional auto-bin range is unsupported", metric="functional", object=object_name)
                    count = None
                else:
                    if len(fields) <= numeric_columns or not all(value.isdigit() for value in fields[-numeric_columns:]):
                        raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional bin row is compressed or unsupported", metric="functional", object=object_name)
                    if not expanded and int(fields[-1]) != 1:
                        raise XcovError("URG_DETAIL_PARSE_INCOMPLETE", "functional bin row is not expanded", metric="functional", object=object_name)
                    if expanded and summary.group(1) == "Cross":
                        bin_name = " ".join(f"[{part}]" for part in bin_parts)
                    else:
                        bin_name = " ".join(bin_parts)
                    count = int(fields[-numeric_columns])
                object_rows += bin_count
                full_name = ".".join(
                    value for value in (scope, covergroup, object_name, bin_name) if value
                )
                row = {
                    "metric": "functional",
                    "type": "npiCovCoverBin",
                    "scope": scope or None,
                    "name": bin_name,
                    "full_name": full_name,
                    "covergroup": covergroup,
                    "coverpoint": object_name if summary.group(1) == "Variable" else None,
                    "cross": object_name if summary.group(1) == "Cross" else None,
                    "bin": bin_name,
                    "covered": 0,
                    "coverable": bin_count,
                    "count": count,
                    "evidence": evidence,
                }
                rows.append(row)
            if expected is not None and object_rows != expected:
                raise XcovError(
                    "URG_DETAIL_PARSE_INCOMPLETE", "functional gap count does not match URG summary",
                    metric="functional", object=object_name, expected=expected, parsed=object_rows,
                )
    # URG may emit both covergroup-type and group-instance views of the same
    # semantic bin. Preserve distinct scopes but remove exact duplicate views.
    unique: Dict[tuple[Any, ...], Json] = {}
    for row in rows:
        key = (
            row.get("scope"), row.get("covergroup"), row.get("coverpoint"),
            row.get("cross"), row.get("bin"), row.get("full_name"),
        )
        unique.setdefault(key, row)
    return list(unique.values())


def write_gap_artifacts(output_dir: str, metric: str, payload: Json) -> Json:
    root = Path(output_dir)
    json_path = root / f"{metric}.json"
    xout_path = root / f"{metric}.xout"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = ["gap_id", "scope", "kind", "name", "covergroup", "coverpoint", "cross", "bin", "covered", "coverable"]
    lines = ["\t".join(columns)]
    for gap in payload["gaps"]:
        lines.append("\t".join("" if gap.get(key) is None else str(gap[key]) for key in columns))
    xout_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"metric": metric, "json": str(json_path), "xout": str(xout_path), "gap_count": payload["gap_count"]}
