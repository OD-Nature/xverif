"""Backends for xdebug MCP tools."""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

from .session_manager import McpSessionManager


Json = Dict[str, Any]


def error_payload(code: str, message: str, **extra: Any) -> Json:
    payload: Json = {"ok": False, "error": {"code": code, "message": message}}
    if extra:
        payload["error"].update(extra)
    return payload


def repo_root() -> str:
    return os.environ.get("XVERIF_HOME") or os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))


def default_xdebug_cmd_json() -> List[str]:
    """xdebug command that forces JSON output."""
    return [os.path.join(repo_root(), "tools", "xdebug"), "--json", "-"]


def default_xdebug_cmd_xout() -> List[str]:
    """xdebug command that uses default (XOUT) output."""
    return [os.path.join(repo_root(), "tools", "xdebug"), "-"]


def _bkill_job(job_name: Optional[str]) -> None:
    """Clean up an LSF job by name using bkill -J."""
    if not job_name:
        return
    bkill_cmd = os.environ.get("XDEBUG_LSF_BKILL", "bkill")
    try:
        subprocess.run([bkill_cmd, "-J", job_name], timeout=10, check=False)
    except Exception:
        pass


def _bkill_by_id(job_id: str) -> None:
    """Clean up an LSF job by ID using bkill <id>."""
    if not job_id:
        return
    bkill_cmd = os.environ.get("XDEBUG_LSF_BKILL", "bkill")
    try:
        subprocess.run([bkill_cmd, job_id], timeout=10, check=False)
    except Exception:
        pass


def _extract_session_id(response: Json, fallback: str) -> str:
    """Extract session_id from xdebug session.open response."""
    for key in ("summary", "data", "session"):
        value = response.get(key)
        if isinstance(value, dict):
            sid = value.get("session_id") or value.get("id")
            if isinstance(sid, str) and sid:
                return sid
    return fallback


# ---------------------------------------------------------------------------
# ManagedSession (moved from old server.py)
# ---------------------------------------------------------------------------


class ManagedSession:
    """In-process session record for the direct backend."""

    def __init__(
        self,
        name: str,
        session_id: str,
        mode: str = "",
        daidir: str = "",
        fsdb: str = "",
        last_summary: Optional[Json] = None,
    ) -> None:
        self.name = name
        self.session_id = session_id
        self.mode = mode
        self.daidir = daidir
        self.fsdb = fsdb
        self.last_used_at = time.time()
        self.last_summary = last_summary or {}

    def to_json(self) -> Json:
        out: Json = {"name": self.name, "session_id": self.session_id, "last_used_at": self.last_used_at}
        if self.mode:
            out["mode"] = self.mode
        if self.daidir:
            out["daidir"] = self.daidir
        if self.fsdb:
            out["fsdb"] = self.fsdb
        if self.last_summary:
            out["last_summary"] = self.last_summary
        return out


# ---------------------------------------------------------------------------
# XdebugRunner
# ---------------------------------------------------------------------------


class XdebugRunner:
    """Runs the ``tools/xdebug`` binary as a subprocess."""

    def __init__(
        self,
        cmd_json: Optional[List[str]] = None,
        cmd_xout: Optional[List[str]] = None,
        timeout_sec: Optional[float] = None,
    ) -> None:
        self.cmd_json = cmd_json or default_xdebug_cmd_json()
        self.cmd_xout = cmd_xout or default_xdebug_cmd_xout()
        self.timeout_sec = timeout_sec or float(os.environ.get("XDEBUG_MCP_TIMEOUT_SEC", "120"))

    def _run_raw(self, request: Json, output_format: str = "json") -> dict:
        """Execute xdebug and return raw {exit_code, stdout, stderr}."""
        cmd = self.cmd_json if output_format in ("json", "envelope") else self.cmd_xout
        try:
            proc = subprocess.run(
                cmd,
                input=json.dumps(request, ensure_ascii=False),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=self.timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"timed out after {self.timeout_sec:g}s"}
        except OSError as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}
        return {"exit_code": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr}

    def request(self, request: Json, output_format: str = "json") -> Any:
        """Run xdebug and return parsed result based on output_format.

        The output_format parameter is optional (default "json") for backward
        compatibility with callers that only pass the request dict.

        - xout  → str (raw xdebug text output)
        - json  → dict (parsed JSON)
        - envelope → dict {exit_code, stdout, stderr, payload_format}
        """
        raw = self._run_raw(request, output_format)

        if output_format == "xout":
            return raw["stdout"]

        if output_format == "json":
            if raw["exit_code"] != 0 and not raw["stdout"].strip():
                return error_payload(
                    "XDEBUG_MCP_EXEC_FAILED",
                    raw["stderr"][-4096:] or f"exit {raw['exit_code']}",
                    exit_code=raw["exit_code"],
                )
            try:
                payload = json.loads(raw["stdout"])
            except Exception as exc:  # noqa: BLE001
                return error_payload(
                    "XDEBUG_MCP_BAD_RESPONSE",
                    f"xdebug did not return JSON: {exc}",
                    exit_code=raw["exit_code"],
                    stdout=raw["stdout"][-4096:],
                    stderr=raw["stderr"][-4096:],
                )
            if isinstance(payload, dict):
                return payload
            return error_payload("XDEBUG_MCP_BAD_RESPONSE", "xdebug JSON response was not an object")

        # envelope
        return {
            "ok": raw["exit_code"] == 0,
            "exit_code": raw["exit_code"],
            "stdout": raw["stdout"],
            "stderr": raw["stderr"],
            "payload_format": "json" if "--json" in self.cmd_json else "xout",
        }


# ---------------------------------------------------------------------------
# DirectBackend (local tools/xdebug)
# ---------------------------------------------------------------------------


class DirectBackend:
    """Direct xdebug runner with in-process session management."""

    def __init__(self, runner: Optional[XdebugRunner] = None) -> None:
        self.runner = runner or XdebugRunner()
        self.sessions: Dict[str, ManagedSession] = {}
        self.default_session: Optional[str] = None

    def ping(self) -> str:
        return "pong"

    def request(self, request: Json, output_format: str = "json") -> Any:
        """Run a raw xdebug request."""
        request = dict(request)
        request.setdefault("api_version", "xdebug.v1")
        request.setdefault("output", {})
        if isinstance(request["output"], dict):
            if output_format in ("json", "envelope"):
                request["output"].setdefault("format", "json")
            else:
                # xout: must NOT have "format":"json" in the JSON body,
                # or xdebug outputs JSON even without the --json CLI flag.
                request["output"].pop("format", None)
        return self.runner.request(request, output_format)

    # -- session management --------------------------------------------------

    def session_open(
        self,
        name: str,
        daidir: Optional[str] = None,
        fsdb: Optional[str] = None,
        queue: Optional[str] = None,
        resource: Optional[str] = None,
        reuse: bool = True,
        reopen: bool = False,
        make_default: bool = True,
    ) -> Json:
        """Open a named xdebug session via session.open action."""
        del queue, resource  # unused in direct mode
        target: Json = {}
        if daidir:
            target["daidir"] = daidir
        if fsdb:
            target["fsdb"] = fsdb
        if not target:
            return error_payload("INVALID_ARGUMENT", "session_open requires daidir and/or fsdb")

        request: Json = {
            "api_version": "xdebug.v1",
            "action": "session.open",
            "target": target,
            "args": {"name": name, "transport": "tcp", "bind_host": "127.0.0.1", "port": 0},
            "output": {"format": "json"},
        }
        if reuse:
            request["args"]["reuse"] = reuse
        if reopen:
            request["args"]["reopen"] = reopen

        response = self.request(request, "json")
        if not isinstance(response, dict):
            return response

        if response.get("ok"):
            session_id = _extract_session_id(response, name)
            record = ManagedSession(
                name,
                session_id,
                mode=str(response.get("summary", {}).get("mode", "")),
                daidir=str(target.get("daidir", "")),
                fsdb=str(target.get("fsdb", "")),
                last_summary=response.get("summary") if isinstance(response.get("summary"), dict) else {},
            )
            self.sessions[name] = record
            self.sessions[session_id] = record
            if make_default:
                self.default_session = session_id
            response.setdefault("mcp", {})
            response["mcp"].update({
                "default_session": self.default_session,
                "managed_session": record.to_json(),
            })
        return response

    def session_list(self, include_native: bool = False) -> Json:
        """List managed sessions."""
        rows: List[Json] = []
        seen = set()
        for record in self.sessions.values():
            if id(record) in seen:
                continue
            seen.add(id(record))
            rows.append(record.to_json())
        out: Json = {"ok": True, "sessions": rows, "default_session": self.default_session}
        if include_native:
            out["native"] = self.request(
                {"api_version": "xdebug.v1", "action": "session.list"},
                "json",
            )
        return out

    def session_use(self, key: str) -> Json:
        """Set default session by name or session_id."""
        record = self.sessions.get(key)
        if not record:
            return error_payload("SESSION_NOT_MANAGED", f"session is not known to this MCP server: {key}")
        record.last_used_at = time.time()
        self.default_session = record.session_id
        return {"ok": True, "default_session": self.default_session, "session": record.to_json()}

    def session_close(self, key: str) -> Json:
        """Close a managed session."""
        record = self.sessions.get(key)
        session_id = record.session_id if record else key
        response = self.request(
            {"api_version": "xdebug.v1", "action": "session.close", "target": {"session_id": session_id}},
            "json",
        )
        if isinstance(response, dict) and (response.get("ok") or record):
            self._remove_session(session_id)
            if record:
                self._remove_session(record.name)
        if isinstance(response, dict):
            response.setdefault("mcp", {})
            response["mcp"]["default_session"] = self.default_session
        return response if isinstance(response, dict) else response

    # -- query ---------------------------------------------------------------

    def query(
        self,
        action: str,
        args: Optional[Json] = None,
        target: Optional[Json] = None,
        session: Optional[str] = None,
        limits: Optional[Json] = None,
        output: Optional[Json] = None,
        output_format: str = "xout",
    ) -> Any:
        """Run an xdebug action, resolving session/target."""
        request: Json = {"api_version": "xdebug.v1", "action": action}
        if args:
            request["args"] = args
        if limits:
            request["limits"] = limits

        # Resolve target
        if target:
            request["target"] = target
        else:
            record = self.sessions.get(session) if isinstance(session, str) else None
            sid = record.session_id if record else (session if isinstance(session, str) else self.default_session)
            if not sid:
                return error_payload("SESSION_REQUIRED", "provide target/session or call xdebug_session_open first")
            request["target"] = {"session_id": sid}
            if record:
                record.last_used_at = time.time()

        # Output control
        request["output"] = output or {}
        if output_format in ("json", "envelope"):
            request["output"]["format"] = "json"

        return self.request(request, output_format)

    # -- internal -----------------------------------------------------------

    def _remove_session(self, key: str) -> None:
        record = self.sessions.pop(key, None)
        if record:
            self.sessions.pop(record.name, None)
            self.sessions.pop(record.session_id, None)
            if self.default_session == record.session_id:
                self.default_session = None
        elif self.default_session == key:
            self.default_session = None


# ---------------------------------------------------------------------------
# LsfBackend (LSF cluster + router + per-session TCP)
# ---------------------------------------------------------------------------


class LsfBackend:
    def __init__(self, fake: Optional[bool] = None) -> None:
        self.fake = fake if fake is not None else os.environ.get("XDEBUG_MCP_FAKE_LSF") == "1"
        bsub_cmd = os.environ.get("XDEBUG_LSF_BSUB")
        if self.fake and not bsub_cmd:
            bsub_cmd = f"{os.sys.executable} -m xdebug_lsf.fake_bsub"
        self.bsub = BsubRunner(bsub_cmd)
        self.router: Optional[RouterClient] = None
        self.sessions: Dict[str, SessionInfo] = {}
        self.default_session: Optional[str] = None
        self.session_launcher = SessionLauncher(self.bsub, fake=self.fake)
        # Stable job name prefix so all jobs from this MCP server share the same root
        import getpass, re, uuid as _uuid

        def _safe_name(s: str) -> str:
            return re.sub(r"[^A-Za-z0-9_]", "_", s)

        self._job_prefix = f"xdebug_{_safe_name(getpass.getuser())}_{os.getpid()}_{_uuid.uuid4().hex[:8]}"
        # Queues: separate for router and session, default "interactive"
        self._router_queue = os.environ.get("XDEBUG_LSF_ROUTER_QUEUE", "interactive")
        self._session_queue = os.environ.get("XDEBUG_LSF_SESSION_QUEUE", "interactive")

    # -- router lifecycle --------------------------------------------------

    def ping(self) -> str:
        # No router needed for ping when no sessions exist
        if not self.sessions:
            return "pong (no sessions)"
        if self.router is None or self.router.process.proc.poll() is not None:
            return "pong (router not running)"
        rsp = self.router.ping()
        return "pong" if rsp.get("ok") else json.dumps(rsp)

    def ensure_router(self) -> RouterClient:
        if self.router is not None and self.router.process.proc.poll() is None:
            return self.router
        router_job = f"{self._job_prefix}_router"
        self.router = RouterClient.start(
            self.bsub, router_job_name=router_job,
            opts=BsubOptions(queue=self._router_queue, job_name=router_job),
        )
        # Re-register all alive sessions
        seen = set()
        for info in list(self.sessions.values()):
            if id(info) in seen:
                continue
            seen.add(id(info))
            if info.state == "alive":
                self.router.register(self._router_session(info))
        return self.router

    def _kill_router(self) -> None:
        """Kill the router job if running."""
        if self.router is None:
            return
        if self.router.process:
            # Prefer job_id for bkill
            jid = getattr(self.router.process, "job_id", None)
            if jid:
                _bkill_by_id(jid)
            else:
                _bkill_job(getattr(self.router.process, "job_name", None))
        self.router.close()
        self.router = None

    # -- session lifecycle --------------------------------------------------

    def _launch_session(self, info: SessionInfo) -> None:
        """Actually launch a pending session job and register with router."""
        launched = self.session_launcher.open(
            info.alias, info.fsdb, info.daidir,
            queue=self._session_queue, job_prefix=self._job_prefix,
        )
        # Copy fields from launched to existing info
        info.session_id = launched.session_id
        info.host = launched.host
        info.port = launched.port
        info.token = launched.token
        info.pid = launched.pid
        info.process = launched.process
        info.job_id = launched.job_id
        info.job_name = launched.job_name
        info.state = "alive"
        # Also index by session_id
        self.sessions[launched.session_id] = info
        # Update default_session if it was pointing to the alias
        if self.default_session == info.alias:
            self.default_session = launched.session_id
        # Register with router
        if self.router:
            self.router.register(self._router_session(info))

    def session_open(
        self,
        name: str,
        fsdb: str,
        daidir: Optional[str] = None,
        queue: Optional[str] = None,
        resource: Optional[str] = None,
        make_default: bool = True,
        **kwargs: Any,
    ) -> Json:
        """Record a session intent — does NOT launch a job until first query."""
        del kwargs
        if not isinstance(name, str) or not name:
            return error_payload("INVALID_ARGUMENT", "session_open requires name")
        if not isinstance(fsdb, str) or not fsdb:
            return error_payload("INVALID_ARGUMENT", "LSF session_open requires fsdb")

        # Override queue from env if not explicitly passed
        actual_queue = queue or self._session_queue

        info = SessionInfo(
            alias=name,
            session_id=name,  # placeholder until launch
            job_name=f"{self._job_prefix}_sess_{name}",
            host="", port=0, token="", pid=None,
            fsdb=fsdb, daidir=daidir,
            state="pending",
        )
        self.sessions[name] = info
        self.sessions[info.session_id] = info
        if make_default:
            self.default_session = info.session_id
        return {"ok": True, "session": info.public_json(), "default_session": self.default_session}

    def _router_session(self, info: SessionInfo) -> Json:
        return {"session_id": info.session_id, "host": info.host, "port": info.port, "token": info.token}

    def query(
        self,
        session: Optional[str],
        action: str,
        args: Optional[Json],
        output_format: str = "xout",
        **kwargs: Any,
    ) -> Any:
        del kwargs
        key = session or self.default_session
        if not key:
            return error_payload("SESSION_REQUIRED", "provide session or call xdebug_session_open")
        info = self.sessions.get(key)
        if not info:
            return error_payload("SESSION_DEAD", f"session not found: {key}")

        # Lazy start: launch pending session on first query
        if info.state == "pending":
            self.ensure_router()
            self._launch_session(info)

        if info.state != "alive":
            return error_payload("SESSION_DEAD", f"session not alive: {key}")

        request = {"api_version": "xdebug.v1", "action": action, "args": args or {}}
        router = self.ensure_router()
        rsp = router.query(info.session_id, request, output_format)
        if not rsp.get("ok"):
            if rsp.get("error", {}).get("code") == "session_dead":
                info.state = "dead"
            return rsp
        if output_format == "xout":
            return rsp.get("xout", "")
        if output_format == "json":
            return rsp.get("json", rsp)
        return rsp

    def session_close(self, session: str) -> Json:
        info = self.sessions.get(session)
        if not info:
            return error_payload("SESSION_NOT_FOUND", session)
        info.state = "closed"
        if self.router:
            self.router.unregister(info.session_id)
        if info.process:
            self._kill_session(info)
        self.sessions.pop(info.alias, None)
        self.sessions.pop(info.session_id, None)
        if self.default_session == info.session_id:
            self.default_session = None
        # If this was the last alive session, kill the router too
        if not any(s.state == "alive" for s in self.sessions.values()):
            self._kill_router()
        return {"ok": True, "closed": info.public_json(), "default_session": self.default_session}

    def _kill_session(self, info: SessionInfo) -> None:
        """Kill a session job — prefer job_id, fallback to job_name."""
        if info.job_id:
            _bkill_by_id(info.job_id)
        elif info.job_name:
            _bkill_job(info.job_name)
        info.process.terminate()
        info.state = "dead"

    def session_list(self, include_native: bool = False) -> Json:
        del include_native
        seen = set()
        rows = []
        for info in self.sessions.values():
            if id(info) in seen:
                continue
            seen.add(id(info))
            rows.append(info.public_json())
        return {"ok": True, "sessions": rows, "default_session": self.default_session}

    def session_use(self, session: str) -> Json:
        info = self.sessions.get(session)
        if not info or info.state not in ("alive", "pending"):
            return error_payload("SESSION_NOT_FOUND", f"session is not alive or unknown: {session}")
        self.default_session = info.session_id
        return {"ok": True, "default_session": self.default_session, "session": info.public_json()}

    def close(self) -> None:
        """Close the entire LSF backend, cleaning up router and all sessions."""
        for info in list(self.sessions.values()):
            if info.process:
                self._kill_session(info)
            info.state = "closed"
        self.sessions.clear()
        self._kill_router()
        self.default_session = None


# ---------------------------------------------------------------------------
# XDebugMcpBackend (unified dispatch)
# ---------------------------------------------------------------------------


class XDebugMcpBackend:
    """Unified backend using McpSessionManager for loop sessions.

    - session_open / query / close  → McpSessionManager (direct or LSF via launcher)
    - request (xdebug_direct_request) → one-shot XdebugRunner for backward compat
    """

    def __init__(
        self,
        mode: Optional[str] = None,
        runner: Optional[XdebugRunner] = None,
    ) -> None:
        self.mode = mode or os.environ.get("XDEBUG_MCP_BACKEND", "direct")
        self._runner = runner or XdebugRunner()
        self._sessions = McpSessionManager(mode=self.mode)
        # Backward compat: old server_legacy checks self.lsf
        self.lsf = self._sessions if self.mode == "lsf" else None
        self.direct = DirectBackend(self._runner)

    def ping(self) -> str:
        return "pong"

    def request(self, request: Json, output_format: str = "json") -> Any:
        """Raw one-shot xdebug request (legacy compatibility)."""
        return DirectBackend(self._runner).request(request, output_format)

    def session_open(self, name: str, **kwargs: Any) -> Json:
        return self._sessions.open_session(name=name, **kwargs)

    def session_list(self, **kwargs: Any) -> Json:
        return self._sessions.list_sessions()

    def session_use(self, key: str) -> Json:
        return self._sessions.use_session(key)

    def session_close(self, key: str) -> Json:
        return self._sessions.close_session(key)

    def query(self, **kwargs: Any) -> Any:
        return self._sessions.query(**kwargs)
