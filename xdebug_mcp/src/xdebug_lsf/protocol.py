"""Shared JSONL process protocol helpers."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Iterable, List, Optional


Json = Dict[str, Any]


class ProtocolError(RuntimeError):
    pass


@dataclass
class JsonlProcess:
    argv: List[str]
    proc: subprocess.Popen[str]
    stdout_queue: "queue.Queue[str]" = field(default_factory=queue.Queue)
    stderr_tail: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    pending: Dict[str, Json] = field(default_factory=dict)
    read_lock: threading.Lock = field(default_factory=threading.Lock)
    job_name: Optional[str] = None
    job_id: Optional[str] = None
    _stdout_thread: Optional[threading.Thread] = None
    _stderr_thread: Optional[threading.Thread] = None

    @classmethod
    def start(cls, argv: Iterable[str]) -> "JsonlProcess":
        args = list(argv)
        proc = subprocess.Popen(
            args,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        item = cls(args, proc)
        item._stdout_thread = threading.Thread(target=item._read_stdout, daemon=True)
        item._stderr_thread = threading.Thread(target=item._read_stderr, daemon=True)
        item._stdout_thread.start()
        item._stderr_thread.start()
        return item

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        from xdebug_lsf.bsub import parse_lsf_job_id as _parse
        for line in self.proc.stdout:
            stripped = line.rstrip("\n")
            if not self.job_id:
                jid = _parse(stripped)
                if jid:
                    self.job_id = jid
            self.stdout_queue.put(stripped)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        # Lazy import to avoid circular dependency
        from xdebug_lsf.bsub import parse_lsf_job_id as _parse
        for line in self.proc.stderr:
            stripped = line.rstrip("\n")
            self.stderr_tail.append(stripped)
            if not self.job_id:
                jid = _parse(stripped)
                if jid:
                    self.job_id = jid

    def wait_ready(self, protocol: str, timeout_sec: float = 30.0) -> Json:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise ProtocolError(f"process exited before ready: rc={self.proc.returncode}")
            try:
                line = self.stdout_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                msg = json.loads(line)
            except Exception:
                continue
            if msg.get("type") == "ready" and msg.get("protocol") == protocol:
                return msg
        raise ProtocolError(f"timeout waiting for ready protocol {protocol}")

    def request(self, obj: Json, timeout_sec: float = 30.0) -> Json:
        """Send a JSONL request and wait for the matching response."""
        req_id = obj.get("request_id") or obj.get("id") or "unknown"
        self.write_json(obj)
        return self.read_json_response(req_id, timeout_sec)

    def write_json(self, msg: Json) -> None:
        if self.proc.stdin is None:
            raise ProtocolError("process stdin is closed")
        self.proc.stdin.write(json.dumps(msg, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.proc.stdin.flush()

    def read_json_response(self, request_id: str, timeout_sec: float = 30.0) -> Json:
        deadline = time.time() + timeout_sec
        with self.read_lock:
            cached = self.pending.pop(request_id, None)
            if cached is not None:
                return cached
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise ProtocolError(f"process exited while waiting response: rc={self.proc.returncode}")
                try:
                    line = self.stdout_queue.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    msg = json.loads(line)
                except Exception as exc:
                    raise ProtocolError(f"stdout protocol pollution after ready: {line!r}") from exc
                msg_id = msg.get("id")
                if msg_id == request_id:
                    return msg
                if isinstance(msg_id, str) and msg_id:
                    self.pending[msg_id] = msg
        raise ProtocolError(f"timeout waiting response {request_id}")

    def terminate(self, timeout_sec: float = 5.0) -> None:
        if self.proc.poll() is not None:
            self._close_pipes()
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=timeout_sec)
        self._close_pipes()

    def _close_pipes(self) -> None:
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except Exception:
                pass

    @property
    def stderr_text(self) -> str:
        return "\n".join(self.stderr_tail)
