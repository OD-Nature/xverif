from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from runner import ArtifactWriter, CliRunner, CommandRunner


TESTS_ROOT = Path(__file__).resolve().parent
XDEBUG_ROOT = TESTS_ROOT.parent
REPO_ROOT = XDEBUG_ROOT.parent
ENGINE_BIN = XDEBUG_ROOT / "libexec" / "xdebug-engine"
_INITIAL_ENGINE_PIDS: set[int] = set()
_ENGINE_OWNER_TOKEN = ""

if str(TESTS_ROOT) not in sys.path:
    sys.path.insert(0, str(TESTS_ROOT))


def _xdebug_engine_pids() -> set[int]:
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,cmd="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    marker = str(ENGINE_BIN)
    pids: set[int] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if marker not in line:
            continue
        pid_text = line.split(None, 1)[0]
        try:
            pids.add(int(pid_text))
        except ValueError:
            continue
    return pids


def _pid_still_matches_engine(pid: int) -> bool:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "cmd="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return False
    return proc.returncode == 0 and str(ENGINE_BIN) in proc.stdout


def _pid_has_owner_token(pid: int, token: str) -> bool:
    if not token:
        return False
    try:
        environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        return False
    expected = f"XDEBUG_TEST_OWNER_TOKEN={token}".encode("utf-8")
    return expected in environ


def _terminate_pids(pids: set[int]) -> None:
    live = {pid for pid in pids if _pid_still_matches_engine(pid)}
    for pid in sorted(live):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        live = {pid for pid in live if _pid_still_matches_engine(pid)}
        if not live:
            return
        time.sleep(0.05)
    for pid in sorted(live):
        if not _pid_still_matches_engine(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _kill_all_sessions_for_home(xdebug_bin: Path, home: Path) -> None:
    request = {
        "api_version": "xdebug.v1",
        "action": "session.kill",
        "target": {"session_id": "all"},
    }
    env = dict(os.environ)
    env.update({"HOME": str(home), "XVERIF_HOME": str(REPO_ROOT)})
    try:
        subprocess.run(
            [str(xdebug_bin), "--json", "-"],
            input=json.dumps(request) + "\n",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=30,
            check=False,
            cwd=str(REPO_ROOT),
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def pytest_sessionstart(session: pytest.Session) -> None:
    global _INITIAL_ENGINE_PIDS, _ENGINE_OWNER_TOKEN
    _INITIAL_ENGINE_PIDS = _xdebug_engine_pids()
    _ENGINE_OWNER_TOKEN = uuid.uuid4().hex
    os.environ["XDEBUG_TEST_OWNER_TOKEN"] = _ENGINE_OWNER_TOKEN


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    current = _xdebug_engine_pids()
    owned = {
        pid
        for pid in current - _INITIAL_ENGINE_PIDS
        if _pid_has_owner_token(pid, _ENGINE_OWNER_TOKEN)
    }
    _terminate_pids(owned)
    os.environ.pop("XDEBUG_TEST_OWNER_TOKEN", None)


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("xdebug")
    group.addoption(
        "--xdebug-bin",
        default=os.environ.get("XDEBUG_BIN", str(REPO_ROOT / "tools" / "xdebug")),
        help="xdebug wrapper/binary path",
    )
    group.addoption(
        "--xdebug-artifacts",
        default=os.environ.get(
            "XDEBUG_TEST_ARTIFACTS",
            str(XDEBUG_ROOT / "tests" / "artifacts"),
        ),
        help="failure artifact root",
    )


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def xdebug_root() -> Path:
    return XDEBUG_ROOT


@pytest.fixture(scope="session")
def xdebug_bin(pytestconfig: pytest.Config) -> Path:
    return Path(pytestconfig.getoption("--xdebug-bin")).expanduser().resolve()


@pytest.fixture
def complex_wave_fsdb(xverif_fixture) -> Path:
    return xverif_fixture("xdebug.ai_complex_wave") / "out/waves.fsdb"


@pytest.fixture
def stream_wave_fsdb(xverif_fixture) -> Path:
    return xverif_fixture("xdebug.stream_v1") / "out/waves.fsdb"


@pytest.fixture(scope="session")
def artifact_root(pytestconfig: pytest.Config) -> Path:
    return Path(pytestconfig.getoption("--xdebug-artifacts")).expanduser().resolve()


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    return home


@pytest.fixture(autouse=True)
def cleanup_xdebug_sessions_after_test(request: pytest.FixtureRequest) -> None:
    yield
    home = getattr(request.node, "funcargs", {}).get("isolated_home")
    if home is None:
        return
    xdebug_bin = Path(request.config.getoption("--xdebug-bin")).expanduser().resolve()
    _kill_all_sessions_for_home(xdebug_bin, home)


@pytest.fixture
def cli_runner(
    xdebug_bin: Path,
    repo_root: Path,
    isolated_home: Path,
) -> CliRunner:
    return CliRunner(
        xdebug_bin,
        cwd=repo_root,
        base_env={"HOME": str(isolated_home), "XVERIF_HOME": str(repo_root)},
    )


@pytest.fixture
def command_runner(repo_root: Path, isolated_home: Path) -> CommandRunner:
    return CommandRunner(
        cwd=repo_root,
        base_env={"HOME": str(isolated_home), "XVERIF_HOME": str(repo_root)},
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" or not report.failed:
        return

    artifact_root = Path(item.config.getoption("--xdebug-artifacts")).expanduser()
    writer = ArtifactWriter(artifact_root, run_id="pytest-failures")
    seen_results: set[int] = set()
    written: list[str] = []
    errors: list[str] = []

    for fixture_name, fixture_value in item.funcargs.items():
        history = getattr(fixture_value, "history", None)
        if not history:
            continue
        transcript = getattr(fixture_value, "transcript", None)
        for index, result in enumerate(history, start=1):
            if id(result) in seen_results:
                continue
            seen_results.add(id(result))
            extra = {}
            if transcript is not None:
                extra["session_log"] = transcript
            case_name = "%s/%s-%02d" % (item.nodeid, fixture_name, index)
            try:
                case_dir = writer.write(case_name, result, extra=extra)
                written.append(str(case_dir))
            except Exception as exc:  # pragma: no cover - best-effort on failure path
                errors.append("%s: %s" % (fixture_name, exc))

    if written or errors:
        text = ""
        if written:
            text += "artifact_dirs:\n" + "\n".join(written)
        if errors:
            text += ("\n" if text else "") + "artifact_errors:\n" + "\n".join(errors)
        item.add_report_section("call", "xdebug artifacts", text)
