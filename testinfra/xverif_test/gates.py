from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import fnmatch
import subprocess

from .catalog import Catalog, SelectedSuite


@dataclass(frozen=True)
class ExecutionPlan:
    gate: str
    suites: tuple[SelectedSuite, ...]

    def render(self) -> str:
        lines = [f"xverif gate: {self.gate}", f"selected suites: {len(self.suites)}"]
        for selected in self.suites:
            mode = "required" if selected.required else "optional"
            suite = selected.suite
            lines.append(
                f"- {suite.id} [{mode}] level={suite.level} cost={suite.cost_class}: "
                f"{selected.reason}"
            )
        return "\n".join(lines)

    def selected_ids(self) -> set[str]:
        return {item.suite.id for item in self.suites}


def build_plan(catalog: Catalog, gate: str) -> ExecutionPlan:
    return ExecutionPlan(gate=gate, suites=catalog.select_gate(gate))


def filter_plan(plan: ExecutionPlan, suite_ids: list[str]) -> ExecutionPlan:
    if not suite_ids:
        return plan
    requested = set(suite_ids)
    available = plan.selected_ids()
    missing = sorted(requested - available)
    if missing:
        raise ValueError(
            f"suite selection is not part of gate {plan.gate}: {', '.join(missing)}"
        )
    return ExecutionPlan(
        gate=plan.gate,
        suites=tuple(item for item in plan.suites if item.suite.id in requested),
    )


def changed_paths(repo_root: Path, base: str) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTUXB", base, "--"],
        cwd=repo_root,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"cannot compute changed paths against {base!r}: {result.stderr.strip()}")
    return tuple(sorted(line for line in result.stdout.splitlines() if line))


def filter_changed(plan: ExecutionPlan, paths: tuple[str, ...]) -> ExecutionPlan:
    if not paths:
        return ExecutionPlan(gate=plan.gate, suites=())
    selected: list[SelectedSuite] = []
    unknown = False
    for entry in plan.suites:
        patterns = [str(value) for value in entry.suite.impact.get("owns", [])]
        if not patterns:
            unknown = True
            continue
        if any(fnmatch.fnmatch(path, pattern) for path in paths for pattern in patterns):
            selected.append(
                SelectedSuite(entry.suite, entry.required, "changed path matched suite impact")
            )
    if unknown:
        return ExecutionPlan(
            gate=plan.gate,
            suites=tuple(
                SelectedSuite(entry.suite, entry.required, "conservative expansion: incomplete impact map")
                for entry in plan.suites
            ),
        )
    return ExecutionPlan(gate=plan.gate, suites=tuple(selected))
