import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def profile(*, verdi_home: str, profile: str = "auto") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["VERDI_HOME"] = verdi_home
    env["XVERIF_EDA_PROFILE"] = profile
    return subprocess.run(
        ["make", "-s", "verdi-profile"], cwd=ROOT, env=env,
        text=True, capture_output=True, check=False,
    )


def test_auto_detects_verdi_2018_and_lowercase_library_fallback() -> None:
    result = profile(verdi_home="/nonexistent/Verdi_O-2018.09-SP2")
    assert result.returncode == 0, result.stderr
    assert "profile=verdi-2018" in result.stdout
    assert "share/NPI/lib/linux64" in result.stdout


def test_auto_preserves_modern_profile_for_versionless_install() -> None:
    result = profile(verdi_home="/nonexistent/verdi-current")
    assert result.returncode == 0, result.stderr
    assert "profile=verdi-2023" in result.stdout


def test_explicit_profile_overrides_path_detection() -> None:
    result = profile(verdi_home="/nonexistent/Verdi_O-2018.09-SP2", profile="verdi-2023")
    assert result.returncode == 0, result.stderr
    assert "profile=verdi-2023" in result.stdout


def test_unknown_profile_fails_without_fallback() -> None:
    result = profile(verdi_home="/nonexistent/verdi", profile="unsupported")
    assert result.returncode != 0
    assert "unsupported XVERIF_EDA_PROFILE" in result.stderr
