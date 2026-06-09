"""Launchers for xdebug --stdio-loop processes (direct and LSF)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Optional

from xdebug_lsf.bsub import BsubOptions, BsubRunner
from xdebug_lsf.protocol import JsonlProcess


def repo_root() -> str:
    return os.environ.get("XVERIF_HOME") or os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../../..")
    )


def default_xdebug_bin() -> str:
    return os.path.join(repo_root(), "tools", "xdebug")


@dataclass
class LaunchConfig:
    alias: str
    xdebug_bin: str
    queue: Optional[str] = None
    resource: Optional[str] = None
    job_name: Optional[str] = None
    startup_timeout_sec: float = 60.0


def _bkill_by_id(job_id: str) -> None:
    bkill_cmd = os.environ.get("XDEBUG_LSF_BKILL", "bkill")
    import subprocess
    try:
        subprocess.run([bkill_cmd, job_id], timeout=10, check=False)
    except Exception:
        pass


class Launcher:
    mode: str = "unknown"

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        raise NotImplementedError

    def terminate(self, handle: JsonlProcess) -> None:
        handle.terminate()


class DirectLauncher(Launcher):
    mode = "direct"

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        cmd = [cfg.xdebug_bin, "--stdio-loop"]
        proc = JsonlProcess.start(cmd)
        proc.job_name = None
        proc.job_id = None
        return proc


class LsfLauncher(Launcher):
    mode = "lsf"

    def __init__(self, bsub: Optional[BsubRunner] = None) -> None:
        bsub_cmd = os.environ.get("XDEBUG_LSF_BSUB")
        if bsub is None and os.environ.get("XDEBUG_MCP_FAKE_LSF") == "1" and not bsub_cmd:
            bsub_cmd = f"{sys.executable} -m xdebug_lsf.fake_bsub"
        self.bsub = bsub or BsubRunner(bsub_cmd)

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        cmd = [cfg.xdebug_bin, "--stdio-loop"]
        proc = self.bsub.start(
            cmd,
            BsubOptions(
                queue=cfg.queue,
                resource=cfg.resource,
                job_name=cfg.job_name,
            ),
        )
        return proc

    def terminate(self, handle: JsonlProcess) -> None:
        try:
            handle.terminate()
        finally:
            jid = getattr(handle, "job_id", None)
            jname = getattr(handle, "job_name", None)
            if jid:
                _bkill_by_id(jid)
            elif jname:
                import subprocess
                bkill_cmd = os.environ.get("XDEBUG_LSF_BKILL", "bkill")
                try:
                    subprocess.run([bkill_cmd, "-J", jname], timeout=10, check=False)
                except Exception:
                    pass
