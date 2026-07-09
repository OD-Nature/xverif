"""Launchers for --stdio-loop backend processes (direct and LSF)."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Optional

from xverif_loop.lsf.bsub import BsubOptions, BsubRunner
from xverif_loop.lsf.protocol import JsonlProcess

from xverif_loop.config import bkill_timeout, fake_lsf_enabled
from xverif_loop.logging import argv_hash, log_lsf_event, log_stdio_event


@dataclass
class LaunchConfig:
    alias: str
    xdebug_bin: str
    backend: str = "xdebug"
    tool_bin: Optional[str] = None
    queue: Optional[str] = None
    resource: Optional[str] = None
    job_name: Optional[str] = None
    startup_timeout_sec: float = 60.0


def _bkill_by_id(job_id: str) -> None:
    bkill_cmd = os.environ.get("XVERIF_LSF_BKILL", "bkill")
    try:
        subprocess.run([bkill_cmd, job_id], timeout=bkill_timeout(), check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _loop_cmd(cfg: LaunchConfig) -> list[str]:
    cmd = [cfg.tool_bin or cfg.xdebug_bin, "--stdio-loop"]
    if cfg.backend == "xdebug":
        cmd.append("--json")
    return cmd


class Launcher:
    mode: str = "unknown"

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        raise NotImplementedError

    def terminate(self, handle: JsonlProcess) -> None:
        handle.terminate()


class DirectLauncher(Launcher):
    mode = "direct"

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        cmd = _loop_cmd(cfg)
        log_stdio_event(cfg.alias, "launcher.direct.start", True,
                        backend=cfg.backend, launcher=self.mode,
                        argv_hash=argv_hash(cmd))
        proc = JsonlProcess.start(cmd, log_context={
            "alias": cfg.alias,
            "backend": cfg.backend,
            "launcher": self.mode,
        })
        proc.job_name = None
        proc.job_id = None
        return proc


class LsfLauncher(Launcher):
    mode = "lsf"

    def __init__(self, bsub: Optional[BsubRunner] = None) -> None:
        bsub_cmd = os.environ.get("XVERIF_LSF_BSUB")
        if bsub is None and fake_lsf_enabled() and not bsub_cmd:
            bsub_cmd = f"{sys.executable} -m xverif_loop.lsf.fake_bsub"
        self.bsub = bsub or BsubRunner(bsub_cmd)

    def start(self, cfg: LaunchConfig) -> JsonlProcess:
        cmd = _loop_cmd(cfg)
        log_lsf_event(cfg.alias, "launcher.lsf.start", True,
                      backend=cfg.backend, launcher=self.mode,
                      queue=cfg.queue, resource=cfg.resource,
                      job_name=cfg.job_name, argv_hash=argv_hash(cmd))
        proc = self.bsub.start(
            cmd,
            BsubOptions(
                queue=cfg.queue,
                resource=cfg.resource,
                job_name=cfg.job_name,
            ),
            log_context={
                "alias": cfg.alias,
                "backend": cfg.backend,
                "launcher": self.mode,
            },
        )
        return proc

    def terminate(self, handle: JsonlProcess) -> None:
        try:
            handle.terminate()
        finally:
            jid = getattr(handle, "job_id", None)
            jname = getattr(handle, "job_name", None)
            if jid:
                log_lsf_event(getattr(handle, "log_alias", None), "bkill.by_id", True,
                              job_id=jid, job_name=jname)
                _bkill_by_id(jid)
            elif jname:
                bkill_cmd = os.environ.get("XVERIF_LSF_BKILL", "bkill")
                try:
                    log_lsf_event(getattr(handle, "log_alias", None), "bkill.by_name", True,
                                  job_name=jname)
                    subprocess.run([bkill_cmd, "-J", jname], timeout=bkill_timeout(), check=False,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
