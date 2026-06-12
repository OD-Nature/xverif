"""文本解释生成器 — 从 TimelineIR 生成人类可读文本解释。"""

from __future__ import annotations

from xsva.ir.timeline import TimelineIR


def render_timeline_text(timeline: TimelineIR) -> str:
    """从 TimelineIR 生成文本解释。"""

    lines: list[str] = []
    sep = "═" * 50

    lines.append(sep)
    lines.append(f"Property: {timeline.property_name}")

    # Clock
    if timeline.clock.signal:
        lines.append(f"Clock: @({timeline.clock.edge} {timeline.clock.signal})")

    # Disable
    if timeline.disable_expr:
        lines.append(f"Disable: disable iff ({timeline.disable_expr})")

    lines.append("")

    # Trigger
    if timeline.trigger:
        lines.append(f"Trigger:")
        lines.append(f"  cycle 0: {_describe_trigger(timeline)}")
        lines.append("")

    if timeline.semantic_notes:
        lines.append("Semantic notes:")
        for note in timeline.semantic_notes:
            lines.append(f"  - {note.text}")
        lines.append("")
        _append_diagnostics(lines, timeline)
        lines.append(sep)
        return "\n".join(lines)

    # Obligations / Paths fallback for timelines without user-facing summaries.
    if len(timeline.paths) == 1 and len(timeline.paths[0].obligations) == 1:
        # 单 obligation — 简化输出
        ob = timeline.paths[0].obligations[0]
        lines.append(f"Obligation:")
        lines.append(f"  {ob.description}")
        if ob.window:
            lines.append(f"  Window: cycle +{ob.window.min_cycle} to "
                         f"+{ob.window.max_cycle if ob.window.max_cycle is not None else '∞'}")
        if ob.failure_condition:
            lines.append(f"  Failure: {ob.failure_condition}")
    elif len(timeline.paths) == 1:
        # 单路径多 obligation
        lines.append("Obligations:")
        for ob in timeline.paths[0].obligations:
            lines.append(f"  [{ob.kind.value}] {ob.description}")
    else:
        # 多路径
        lines.append(f"Obligations ({len(timeline.paths)} paths):")
        for path in timeline.paths:
            lines.append(f"  {path.description}:")
            for ob in path.obligations:
                lines.append(f"    [{ob.kind.value}] {ob.description}")

    # Failure conditions
    if timeline.failure_conditions:
        lines.append("")
        lines.append("Failure conditions:")
        for fc in timeline.failure_conditions:
            lines.append(f"  {fc.condition}")

    _append_diagnostics(lines, timeline)

    lines.append(sep)
    return "\n".join(lines)


def _append_diagnostics(lines: list[str], timeline: TimelineIR) -> None:
    if timeline.diagnostics:
        lines.append("")
        lines.append("Diagnostics:")
        for d in timeline.diagnostics:
            lines.append(f"  [{d.severity}] {d.code}: {d.message}")


def _describe_trigger(timeline: TimelineIR) -> str:
    """描述触发条件。"""
    if timeline.trigger_expr:
        desc = timeline.trigger_expr
    else:
        desc = "trigger condition"

    # Add capture info
    if timeline.trigger_captures:
        caps = []
        for c in timeline.trigger_captures:
            caps.append(f"{c['var']} = {c['expr']}")
        desc += f" (captures: {', '.join(caps)})"

    return desc
