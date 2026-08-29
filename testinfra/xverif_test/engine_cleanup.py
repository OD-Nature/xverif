from __future__ import annotations

import os
import signal
import subprocess
import time
import uuid
from pathlib import Path


OWNER_ENV = "XDEBUG_TEST_OWNER_TOKEN"


class EngineProcessGuard:
    def __init__(self, engine_bin: Path) -> None:
        self.engine_bin = engine_bin.resolve()
        self.marker = str(self.engine_bin)
        self.initial_pids: set[int] = set()
        self.token = uuid.uuid4().hex

    def start(self) -> None:
        self.initial_pids = self.engine_pids()
        os.environ[OWNER_ENV] = self.token

    def engine_pids(self) -> set[int]:
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
        pids: set[int] = set()
        for line in proc.stdout.splitlines():
            line = line.strip()
            if self.marker not in line:
                continue
            try:
                pids.add(int(line.split(None, 1)[0]))
            except ValueError:
                continue
        return pids

    def _pid_matches(self, pid: int) -> bool:
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
        return proc.returncode == 0 and self.marker in proc.stdout

    def _pid_owned(self, pid: int) -> bool:
        try:
            environ = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
        except OSError:
            return False
        expected = f"{OWNER_ENV}={self.token}".encode("utf-8")
        return expected in environ

    def owned_pids(self) -> set[int]:
        return {
            pid
            for pid in self.engine_pids() - self.initial_pids
            if self._pid_owned(pid)
        }

    def cleanup(self, timeout_sec: float = 2.0) -> set[int]:
        live = {pid for pid in self.owned_pids() if self._pid_matches(pid)}
        for pid in sorted(live):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + timeout_sec
        while live and time.monotonic() < deadline:
            live = {pid for pid in live if self._pid_matches(pid)}
            if live:
                time.sleep(0.05)
        for pid in sorted(live):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if live:
            deadline = time.monotonic() + timeout_sec
            while live and time.monotonic() < deadline:
                live = {pid for pid in live if self._pid_matches(pid)}
                if live:
                    time.sleep(0.05)
        if os.environ.get(OWNER_ENV) == self.token:
            os.environ.pop(OWNER_ENV, None)
        return live
