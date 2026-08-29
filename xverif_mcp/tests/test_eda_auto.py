from pathlib import Path

import pytest

from xverif_mcp.eda_auto import EdaConfigError, _write_machine_config, resolve_environment


def make_verdi(root: Path, version: str) -> Path:
    home = root / f"Verdi_{version}"
    (home / "share/NPI/inc").mkdir(parents=True)
    (home / "share/NPI/lib/LINUX64").mkdir(parents=True)
    (home / "share/PLI/VCS/LINUX64").mkdir(parents=True)
    (home / "bin").mkdir()
    return home


def make_vcs(root: Path, version: str) -> Path:
    home = root / f"VCS_{version}"
    (home / "bin").mkdir(parents=True)
    (home / "linux64").mkdir()
    return home


def test_discovers_single_2018_install(tmp_path: Path) -> None:
    installs = tmp_path / "verdi"
    home = make_verdi(installs, "O-2018.09-SP2")
    vcs_installs = tmp_path / "vcs"
    vcs_home = make_vcs(vcs_installs, "O-2018.09-SP2")
    config = tmp_path / "eda.toml"
    config.write_text(
        f'search_roots = ["{installs}"]\nvcs_search_roots = ["{vcs_installs}"]\n',
        encoding="utf-8",
    )

    env, evidence = resolve_environment(
        cwd=tmp_path, environ={"LD_LIBRARY_PATH": "existing-pli"}, machine_config=config
    )

    assert env["XVERIF_EDA_PROFILE"] == "verdi-2018"
    assert env["VERDI_HOME"] == str(home.resolve())
    assert env["VCS_HOME"] == str(vcs_home.resolve())
    assert env["LD_LIBRARY_PATH"] == f"{home / 'share/PLI/VCS/LINUX64'}:existing-pli"
    assert evidence["selection"] == "discovered"


def test_machine_config_wins_and_loads_private_env(tmp_path: Path) -> None:
    home = make_verdi(tmp_path, "V-2023.12-SP2")
    vcs_home = make_vcs(tmp_path, "V-2023.12-SP2")
    config = tmp_path / "eda.toml"
    config.write_text(
        f'preferred_profile = "verdi-2023"\n'
        f'[profiles.verdi-2023]\nverdi_home = "{home}"\n'
        f'vcs_home = "{vcs_home}"\n'
        '[env]\nSNPSLMD_LICENSE_FILE = "license-server"\n',
        encoding="utf-8",
    )

    env, evidence = resolve_environment(cwd=tmp_path, environ={}, machine_config=config)

    assert env["XVERIF_EDA_PROFILE"] == "verdi-2023"
    assert env["VCS_HOME"] == str(vcs_home.resolve())
    assert env["SNPSLMD_LICENSE_FILE"] == "license-server"
    assert evidence["selection"] == "configured"


def test_project_preference_disambiguates_two_versions(tmp_path: Path) -> None:
    installs = tmp_path / "verdi"
    make_verdi(installs, "O-2018.09-SP2")
    selected = make_verdi(installs, "V-2023.12-SP2")
    vcs_installs = tmp_path / "vcs"
    make_vcs(vcs_installs, "O-2018.09-SP2")
    selected_vcs = make_vcs(vcs_installs, "V-2023.12-SP2")
    machine = tmp_path / "machine.toml"
    machine.write_text(
        f'search_roots = ["{installs}"]\nvcs_search_roots = ["{vcs_installs}"]\n',
        encoding="utf-8",
    )
    project = tmp_path / "project"
    project.mkdir()
    (project / ".xverif-eda.toml").write_text(
        'preferred_profile = "verdi-2023"\n', encoding="utf-8"
    )

    env, evidence = resolve_environment(cwd=project, environ={}, machine_config=machine)

    assert env["VERDI_HOME"] == str(selected.resolve())
    assert env["VCS_HOME"] == str(selected_vcs.resolve())
    assert evidence["project_config"].endswith(".xverif-eda.toml")


def test_auto_rejects_ambiguous_versions(tmp_path: Path) -> None:
    installs = tmp_path / "verdi"
    make_verdi(installs, "O-2018.09-SP2")
    make_verdi(installs, "V-2023.12-SP2")
    vcs_installs = tmp_path / "vcs"
    make_vcs(vcs_installs, "O-2018.09-SP2")
    make_vcs(vcs_installs, "V-2023.12-SP2")
    config = tmp_path / "eda.toml"
    config.write_text(
        f'search_roots = ["{installs}"]\nvcs_search_roots = ["{vcs_installs}"]\n',
        encoding="utf-8",
    )

    with pytest.raises(EdaConfigError, match="exactly one installed profile"):
        resolve_environment(cwd=tmp_path, environ={}, machine_config=config)


def test_machine_init_writes_private_config_without_ld_path(tmp_path: Path) -> None:
    verdi = make_verdi(tmp_path, "O-2018.09-SP2")
    vcs = make_vcs(tmp_path, "O-2018.09-SP2")
    config = tmp_path / "config" / "eda.toml"

    _write_machine_config(
        config,
        profile="verdi-2018",
        verdi_home=verdi,
        vcs_home=vcs,
        environ={"SNPS_LICENSE_FILE": "license-server", "LD_LIBRARY_PATH": "do-not-save"},
    )

    assert config.stat().st_mode & 0o777 == 0o600
    text = config.read_text(encoding="utf-8")
    assert "SNPS_LICENSE_FILE" in text
    assert "LD_LIBRARY_PATH" not in text
