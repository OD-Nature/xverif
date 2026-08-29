from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import socket
import sys
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Iterable, Mapping


class DependencyError(ValueError):
    pass


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    reason: str
    source: str = "probe"


@dataclass(frozen=True)
class DependencyRegistry:
    version: str
    definitions: dict[str, dict[str, Any]]

    @classmethod
    def load(cls, path: Path) -> "DependencyRegistry":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DependencyError(f"cannot load dependency registry {path}: {exc}") from exc
        if raw.get("version") != "xverif-dependency-registry.v1":
            raise DependencyError("unsupported dependency registry version")
        definitions: dict[str, dict[str, Any]] = {}
        for item in raw.get("dependencies", []):
            name = item.get("id")
            if not isinstance(name, str) or not name:
                raise DependencyError("dependency id must be a non-empty string")
            if name in definitions:
                raise DependencyError(f"duplicate dependency id: {name}")
            definitions[name] = dict(item)
        return cls(version=raw["version"], definitions=definitions)

    def require_known(self, names: Iterable[str]) -> None:
        unknown = sorted(set(names) - self.definitions.keys())
        if unknown:
            raise DependencyError("unknown dependencies: " + ", ".join(unknown))


def load_default_dependency_registry(repo_root: Path) -> DependencyRegistry:
    return DependencyRegistry.load(repo_root / "testinfra/dependencies.v1.json")


def probe_dependencies(
    names: Iterable[str],
    repo_root: Path,
    *,
    registry: DependencyRegistry | None = None,
    effective_env: Mapping[str, str] | None = None,
) -> dict[str, DependencyStatus]:
    registry = registry or load_default_dependency_registry(repo_root)
    requested = sorted(set(names))
    registry.require_known(requested)
    env = dict(os.environ if effective_env is None else effective_env)
    return {
        name: _probe(name, registry.definitions[name], repo_root, env)
        for name in requested
    }


def validate_suite_dependencies(catalog: Any, registry: DependencyRegistry) -> None:
    registry.require_known(
        name for suite in catalog.suites for name in suite.capabilities
    )


def _probe(
    name: str, definition: dict[str, Any], repo_root: Path, env: Mapping[str, str]
) -> DependencyStatus:
    kind = definition["kind"]
    if kind == "python_packages":
        failures: list[str] = []
        for distribution, minimum in definition.get("packages", {}).items():
            try:
                installed = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                failures.append(f"{distribution} is not installed")
                continue
            if _version_tuple(installed) < _version_tuple(str(minimum)):
                failures.append(f"{distribution} {installed} < {minimum}")
        if sys.version_info < (3, 11):
            failures.insert(0, f"Python {sys.version.split()[0]} < 3.11")
        return DependencyStatus(name, not failures, "; ".join(failures) or "Python test runtime available")
    if kind == "python_import":
        module = str(definition["module"])
        return DependencyStatus(name, importlib.util.find_spec(module) is not None, f"Python import {module}")
    if kind == "executable":
        command = str(definition["command"])
        resolved = shutil.which(command, path=env.get("PATH"))
        hint = f"{command} executable"
        if command == "nvim" and not resolved:
            local = Path.home() / ".local/bin/nvim"
            if local.is_file():
                hint += "; installed at ~/.local/bin/nvim, add $HOME/.local/bin to PATH"
        return DependencyStatus(name, resolved is not None, hint)
    if kind == "uds":
        return DependencyStatus(name, hasattr(socket, "AF_UNIX"), "AF_UNIX support")
    if kind == "constant":
        return DependencyStatus(name, bool(definition["available"]), str(definition["reason"]))
    if kind == "real_lsf":
        enabled = env.get("XDEBUG_ENABLE_REAL_LSF") == "1"
        commands = {
            "bsub": env.get("XVERIF_LSF_BSUB", "bsub"),
            "bkill": env.get("XVERIF_LSF_BKILL", "bkill"),
            "bjobs": "bjobs",
        }
        missing = [key for key, command in commands.items() if shutil.which(command, path=env.get("PATH")) is None]
        reason = "XDEBUG_ENABLE_REAL_LSF=1 and bsub/bjobs/bkill available"
        if missing:
            reason += "; missing " + ", ".join(missing)
        return DependencyStatus(name, enabled and not missing, reason)
    if kind == "npi":
        home = _env_path(env, "VERDI_HOME")
        libs = [home / "share/NPI/lib/LINUX64", home / "share/NPI/lib/linux64"] if home else []
        license_ok, license_reason = _license_status(env)
        available = home is not None and home.is_dir() and any(path.is_dir() for path in libs) and license_ok
        return DependencyStatus(name, available, "VERDI_HOME NPI runtime; " + license_reason)
    if kind in {"vcs", "vcs_uvm"}:
        executable = shutil.which("vcs", path=env.get("PATH"))
        vcs_home = _env_path(env, "VCS_HOME")
        license_ok, license_reason = _license_status(env)
        uvmdir_ok = kind != "vcs_uvm" or (vcs_home is not None and (vcs_home / "etc/uvm").is_dir())
        available = executable is not None and vcs_home is not None and vcs_home.is_dir() and uvmdir_ok and license_ok
        detail = "vcs executable, VCS_HOME"
        if kind == "vcs_uvm":
            detail += ", VCS_HOME/etc/uvm"
        return DependencyStatus(name, available, detail + "; " + license_reason)
    if kind == "svt_vip":
        protocol = str(definition["protocol"])
        root = _env_path(env, "DESIGNWARE_HOME")
        amba = _env_path(env, "SVT_AMBA_VIP_HOME")
        common = _env_path(env, "SVT_COMMON_HOME")
        vip_inc = _env_path(env, "SVT_VIP_INCDIR") or (amba / "sverilog/include" if amba else None)
        vip_src = _env_path(env, "SVT_VIP_SRCDIR") or (amba / "sverilog/src/vcs" if amba else None)
        common_inc = _env_path(env, "SVT_COMMON_INCDIR") or (common / "sverilog/include" if common else None)
        common_src = _env_path(env, "SVT_COMMON_SRCDIR") or (common / "sverilog/src/vcs" if common else None)
        required = [
            root / "vip/svt" if root else None,
            vip_inc / f"svt_{protocol}_if.svi" if vip_inc else None,
            vip_inc / f"svt_{protocol}.uvm.pkg" if vip_inc else None,
            vip_src,
            common_inc,
            common_src,
        ]
        return DependencyStatus(name, all(path is not None and path.exists() for path in required), f"effective SVT {protocol.upper()} VIP roots and protocol files")
    if kind == "vendored_xif":
        source = repo_root / "third_party/xif_agent/src"
        required = [source / "xif_pkg.sv", source / "xif_if.sv", source / "xif_agent_pkg.sv"]
        return DependencyStatus(name, all(path.is_file() for path in required), "repository third_party/xif_agent compile sources")
    if kind == "fixture_output":
        return DependencyStatus(name, True, f"validated from declared fixture output {definition['output']}", source="fixture")
    raise DependencyError(f"unsupported dependency kind {kind!r} for {name}")


def _env_path(env: Mapping[str, str], name: str) -> Path | None:
    value = env.get(name, "").strip()
    return Path(os.path.expanduser(value)).resolve() if value else None


def _license_status(env: Mapping[str, str]) -> tuple[bool, str]:
    value = env.get("SNPSLMD_LICENSE_FILE", "").strip() or env.get("LM_LICENSE_FILE", "").strip()
    if not value:
        return False, "SNPSLMD_LICENSE_FILE or LM_LICENSE_FILE is unset"
    entries = [item for item in value.split(os.pathsep) if item]
    valid = bool(entries) and all("\n" not in item and "\r" not in item for item in entries)
    return valid, "license configuration present (redacted)" if valid else "license configuration format is invalid"


def _version_tuple(value: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", value)
    return tuple(int(number) for number in numbers[:4])
