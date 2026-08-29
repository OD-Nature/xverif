"""Resolve a local Verdi installation and launch xverif MCP with a safe env."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tomllib


SUPPORTED_PROFILES = ("verdi-2018", "verdi-2023")
# 默认扫描机器级 EDA 安装根下 eda、tools、opt 三个标准根目录中的
# Synopsys Verdi/VCS 安装；路径运行时按 os.sep 拼接，源码不写死绝对字面量。
DEFAULT_SEARCH_ROOTS = tuple(
    os.path.join(os.sep, root, "synopsys", "verdi")
    for root in ("eda", "tools", "opt")
)
DEFAULT_VCS_SEARCH_ROOTS = tuple(
    os.path.join(os.sep, root, "synopsys", leaf)
    for root in ("eda", "tools", "opt")
    for leaf in ("vcs-mx", "vcs")
)
MACHINE_ENV_KEYS = (
    "SNPSLMD_LICENSE_FILE",
    "SNPS_LICENSE_FILE",
    "LM_LICENSE_FILE",
    "MGLS_LICENSE_FILE",
    "CDS_LIC_FILE",
    "SNPS_HOME",
    "VCS_ARCH_OVERRIDE",
    "VCS_TARGET_ARCH",
    "VCS_WORKING_DIR",
)


class EdaConfigError(RuntimeError):
    pass


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as stream:
            value = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise EdaConfigError(f"cannot read EDA config {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EdaConfigError(f"EDA config must be a TOML table: {path}")
    return value


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_machine_config(
    path: Path,
    *,
    profile: str,
    verdi_home: Path,
    vcs_home: Path,
    environ: dict[str, str],
) -> None:
    if path.exists():
        raise EdaConfigError(f"machine config already exists: {path}; remove it explicitly before reinitializing")
    lines = [
        f"preferred_profile = {_toml_string(profile)}",
        "",
        f"[profiles.{profile}]",
        f"verdi_home = {_toml_string(str(verdi_home))}",
        f"vcs_home = {_toml_string(str(vcs_home))}",
    ]
    env_values = [(key, environ[key]) for key in MACHINE_ENV_KEYS if environ.get(key)]
    if env_values:
        lines.extend(["", "[env]"])
        lines.extend(f"{key} = {_toml_string(value)}" for key, value in env_values)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _project_config(start: Path) -> Path | None:
    current = start.resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".xverif-eda.toml"
        if candidate.is_file():
            return candidate
    return None


def _profile_for_path(path: Path) -> str | None:
    name = str(path).lower()
    if "2018" in name:
        return "verdi-2018"
    if "2023" in name:
        return "verdi-2023"
    return None


def _npi_lib(verdi_home: Path) -> Path | None:
    for relative in ("share/NPI/lib/LINUX64", "share/NPI/lib/linux64"):
        candidate = verdi_home / relative
        if candidate.is_dir():
            return candidate
    return None


def _pli_lib(verdi_home: Path) -> Path | None:
    for relative in ("share/PLI/VCS/LINUX64", "share/PLI/VCS/linux64"):
        candidate = verdi_home / relative
        if candidate.is_dir():
            return candidate
    return None


def _valid_install(path: Path) -> bool:
    return (
        path.is_dir()
        and (path / "share/NPI/inc").is_dir()
        and _npi_lib(path) is not None
        and _pli_lib(path) is not None
    )


def _valid_vcs_install(path: Path) -> bool:
    return path.is_dir() and (path / "bin").is_dir() and (path / "linux64").is_dir()


def _discover(
    search_roots: list[Path],
    vcs_search_roots: list[Path],
    inherited_home: str | None,
    inherited_vcs_home: str | None,
) -> tuple[dict[str, list[Path]], dict[str, list[Path]]]:
    found = {profile: [] for profile in SUPPORTED_PROFILES}
    vcs_found = {profile: [] for profile in SUPPORTED_PROFILES}
    candidates: list[Path] = []
    vcs_candidates: list[Path] = []
    if inherited_home:
        candidates.append(Path(inherited_home).expanduser())
    if inherited_vcs_home:
        vcs_candidates.append(Path(inherited_vcs_home).expanduser())
    for root in search_roots:
        root = root.expanduser()
        if _valid_install(root):
            candidates.append(root)
        if root.is_dir():
            candidates.extend(item for item in root.iterdir() if item.is_dir())
    for root in vcs_search_roots:
        root = root.expanduser()
        if _valid_vcs_install(root):
            vcs_candidates.append(root)
        if root.is_dir():
            vcs_candidates.extend(item for item in root.iterdir() if item.is_dir())
    for candidate in candidates:
        profile = _profile_for_path(candidate)
        resolved = candidate.resolve()
        if profile and _valid_install(resolved) and resolved not in found[profile]:
            found[profile].append(resolved)
    for candidate in vcs_candidates:
        profile = _profile_for_path(candidate)
        resolved = candidate.resolve()
        if profile and _valid_vcs_install(resolved) and resolved not in vcs_found[profile]:
            vcs_found[profile].append(resolved)
    return found, vcs_found


def resolve_environment(
    *,
    cwd: Path,
    environ: dict[str, str],
    machine_config: Path | None = None,
) -> tuple[dict[str, str], dict[str, str]]:
    machine_path = machine_config or Path(
        environ.get("XVERIF_EDA_CONFIG", "~/.config/xverif/eda.toml")
    ).expanduser()
    project_path = _project_config(cwd)
    machine = _load_toml(machine_path)
    project = _load_toml(project_path) if project_path else {}

    preferred = str(project.get("preferred_profile", machine.get("preferred_profile", "auto")))
    if preferred not in (*SUPPORTED_PROFILES, "auto"):
        raise EdaConfigError(
            f"unsupported preferred_profile {preferred!r}; expected auto, verdi-2018, or verdi-2023"
        )

    roots_value = project.get("search_roots", machine.get("search_roots", DEFAULT_SEARCH_ROOTS))
    if not isinstance(roots_value, list) and not isinstance(roots_value, tuple):
        raise EdaConfigError("search_roots must be an array of directory paths")
    roots = [Path(str(value)) for value in roots_value]
    vcs_roots_value = project.get(
        "vcs_search_roots", machine.get("vcs_search_roots", DEFAULT_VCS_SEARCH_ROOTS)
    )
    if not isinstance(vcs_roots_value, (list, tuple)):
        raise EdaConfigError("vcs_search_roots must be an array of directory paths")
    vcs_roots = [Path(str(value)) for value in vcs_roots_value]

    configured: dict[str, Path] = {}
    configured_vcs: dict[str, Path] = {}
    profiles = machine.get("profiles", {})
    if profiles and not isinstance(profiles, dict):
        raise EdaConfigError("profiles must be a TOML table")
    for profile in SUPPORTED_PROFILES:
        entry = profiles.get(profile, {}) if isinstance(profiles, dict) else {}
        if entry:
            if not isinstance(entry, dict) or not entry.get("verdi_home"):
                raise EdaConfigError(f"profiles.{profile}.verdi_home is required")
            home = Path(str(entry["verdi_home"])).expanduser().resolve()
            if not _valid_install(home):
                raise EdaConfigError(f"configured {profile} installation is invalid: {home}")
            configured[profile] = home
            vcs_value = entry.get("vcs_home")
            if vcs_value:
                vcs_home = Path(str(vcs_value)).expanduser().resolve()
                if not _valid_vcs_install(vcs_home):
                    raise EdaConfigError(f"configured {profile} VCS installation is invalid: {vcs_home}")
                configured_vcs[profile] = vcs_home

    discovered, discovered_vcs = _discover(
        roots, vcs_roots, environ.get("VERDI_HOME"), environ.get("VCS_HOME")
    )
    available = {
        profile: [configured[profile]] if profile in configured else discovered[profile]
        for profile in SUPPORTED_PROFILES
    }
    available_vcs = {
        profile: [configured_vcs[profile]] if profile in configured_vcs else discovered_vcs[profile]
        for profile in SUPPORTED_PROFILES
    }
    if preferred == "auto":
        present = [profile for profile, paths in available.items() if paths]
        if len(present) != 1:
            detail = ", ".join(f"{profile}={len(available[profile])}" for profile in SUPPORTED_PROFILES)
            raise EdaConfigError(
                "EDA auto-selection requires exactly one installed profile "
                f"({detail}); set preferred_profile in .xverif-eda.toml or configure "
                f"{machine_path}"
            )
        selected = present[0]
    else:
        selected = preferred
    choices = available[selected]
    if len(choices) != 1:
        raise EdaConfigError(
            f"{selected} selection requires exactly one installation, found {len(choices)}; "
            f"configure profiles.{selected}.verdi_home in {machine_path}"
        )

    verdi_home = choices[0]
    vcs_choices = available_vcs[selected]
    if len(vcs_choices) != 1:
        detail = ", ".join(f"{profile}={len(available_vcs[profile])}" for profile in SUPPORTED_PROFILES)
        raise EdaConfigError(
            f"{selected} requires exactly one matching VCS installation ({detail}); "
            f"configure profiles.{selected}.vcs_home or vcs_search_roots in {machine_path}"
        )
    vcs_home = vcs_choices[0]
    npi_lib = _npi_lib(verdi_home)
    pli_lib = _pli_lib(verdi_home)
    assert npi_lib is not None and pli_lib is not None
    result = dict(environ)
    extra_env = machine.get("env", {})
    if extra_env and not isinstance(extra_env, dict):
        raise EdaConfigError("env must be a TOML table")
    for key, value in extra_env.items():
        result[str(key)] = str(value)
    result["VERDI_HOME"] = str(verdi_home)
    result["VCS_HOME"] = str(vcs_home)
    result["XVERIF_EDA_PROFILE"] = selected
    result["PATH"] = os.pathsep.join(
        value for value in (str(verdi_home / "bin"), str(vcs_home / "bin"), result.get("PATH", "")) if value
    )
    ld_paths = [str(pli_lib)]
    ld_paths.extend(value for value in result.get("LD_LIBRARY_PATH", "").split(os.pathsep) if value)
    result["LD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(ld_paths))
    evidence = {
        "profile": selected,
        "verdi_home": str(verdi_home),
        "vcs_home": str(vcs_home),
        "machine_config": str(machine_path) if machine_path.is_file() else "not-used",
        "project_config": str(project_path) if project_path else "not-used",
        "selection": "configured" if selected in configured or selected in configured_vcs else "discovered",
    }
    return result, evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-configure EDA environment for xverif MCP")
    parser.add_argument("--doctor", action="store_true", help="resolve and print non-sensitive evidence")
    parser.add_argument("--init", action="store_true", help="write a user-only machine EDA config from the current environment")
    args, server_args = parser.parse_known_args(argv)
    try:
        env, evidence = resolve_environment(cwd=Path.cwd(), environ=dict(os.environ))
    except EdaConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.init:
        machine_path = Path(
            os.environ.get("XVERIF_EDA_CONFIG", "~/.config/xverif/eda.toml")
        ).expanduser()
        _write_machine_config(
            machine_path,
            profile=evidence["profile"],
            verdi_home=Path(evidence["verdi_home"]),
            vcs_home=Path(evidence["vcs_home"]),
            environ=env,
        )
        print(f"initialized={machine_path}")
        print(f"profile={evidence['profile']}")
        return 0
    if args.doctor:
        for key, value in evidence.items():
            print(f"{key}={value}")
        return 0
    root = Path(env.get("XVERIF_HOME", Path(__file__).resolve().parents[3]))
    command = root / "tools/xverif-mcp"
    if not command.is_file():
        print(f"ERROR: xverif MCP launcher not found: {command}", file=sys.stderr)
        return 2
    os.execvpe(str(command), [str(command), *server_args], env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
