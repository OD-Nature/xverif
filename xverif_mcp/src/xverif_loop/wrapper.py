"""SDK-free UDS JSONL wrapper for xverif stateful loop sessions."""

from __future__ import annotations

import argparse
import json
import os
import socket
import stat
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from xverif_loop.config import (
    configure_loop_wrapper_environment,
    default_xcov_bin,
    default_xdebug_bin,
    loop_backend,
    startup_timeout,
    request_timeout,
)
from xverif_loop.logging import (
    configure_loop_wrapper_logging,
    log_server_event,
    log_uds_event,
)
from xverif_loop.sessions.session_manager import McpSessionManager
from xverif_loop.xdebug_errors import (
    forbidden_native_session_error,
    is_forbidden_native_session_action,
)

Json = Dict[str, Any]


METHOD_PARAM_CONTRACTS: dict[str, dict[str, tuple[str, ...]]] = {
    "server.ping": {"required": (), "optional": (), "any_of": ()},
    "server.shutdown": {"required": (), "optional": (), "any_of": ()},
    "debug.session.open": {
        "required": ("name",),
        "optional": ("fsdb", "daidir", "run_manifest", "queue", "resource"),
        "any_of": ("fsdb", "daidir"),
    },
    "debug.session.list": {
        "required": (), "optional": ("include_tombstones", "verbose"), "any_of": (),
    },
    "debug.session.doctor": {
        "required": (), "optional": ("session", "session_id", "name", "verbose"),
        "any_of": ("session", "session_id", "name"),
    },
    "debug.session.close": {
        "required": (), "optional": ("session", "session_id", "name"),
        "any_of": ("session", "session_id", "name"),
    },
    "debug.session.kill": {
        "required": (), "optional": ("session", "session_id", "name"),
        "any_of": ("session", "session_id", "name"),
    },
    "debug.session.gc": {"required": (), "optional": ("verbose",), "any_of": ()},
    "debug.query": {
        "required": ("session", "action"),
        "optional": ("args", "limits", "output_format"),
        "any_of": (),
    },
    "cov.session.open": {
        "required": ("name", "vdb"),
        "optional": ("run_manifest", "queue", "resource"),
        "any_of": (),
    },
    "cov.session.list": {
        "required": (), "optional": ("include_tombstones", "verbose"), "any_of": (),
    },
    "cov.session.doctor": {
        "required": (), "optional": ("session", "session_id", "name", "verbose"),
        "any_of": ("session", "session_id", "name"),
    },
    "cov.session.close": {
        "required": (), "optional": ("session", "session_id", "name"),
        "any_of": ("session", "session_id", "name"),
    },
    "cov.session.kill": {
        "required": (), "optional": ("session", "session_id", "name"),
        "any_of": ("session", "session_id", "name"),
    },
    "cov.session.gc": {"required": (), "optional": ("verbose",), "any_of": ()},
    "cov.query": {
        "required": ("session", "action"),
        "optional": ("args", "limits", "output", "output_format"),
        "any_of": (),
    },
}


def validate_method_params(method: str, params: Json) -> None:
    contract = METHOD_PARAM_CONTRACTS.get(method)
    if contract is None:
        return
    allowed = set(contract["required"]) | set(contract["optional"])
    unexpected = sorted(set(params) - allowed)
    if unexpected:
        raise TypeError(f"unexpected params for {method}: {', '.join(unexpected)}")
    missing = [key for key in contract["required"] if key not in params]
    if missing:
        raise TypeError(f"missing required params for {method}: {', '.join(missing)}")
    any_of = contract["any_of"]
    if any_of and not any(params.get(key) for key in any_of):
        raise TypeError(f"provide one of for {method}: {', '.join(any_of)}")


def default_socket_path() -> str:
    return os.environ.get(
        "XVERIF_LOOP_SOCKET",
        f"/tmp/xverif-loop-{os.getuid()}.sock",
    )


def _error(code: str, message: str, **extra: Any) -> Json:
    err: Json = {"code": code, "message": message}
    err.update(extra)
    return {"ok": False, "error": err}


def _response(req_id: Any, result: Any) -> Json:
    if isinstance(result, dict) and result.get("ok") is False and isinstance(result.get("error"), dict):
        return {"id": req_id, "ok": False, "error": result["error"]}
    return {"id": req_id, "ok": True, "result": result}


class LoopWrapperService:
    def __init__(
        self,
        *,
        mode: Optional[str] = None,
        xdebug_bin: Optional[str] = None,
        xcov_bin: Optional[str] = None,
        startup_timeout_sec: Optional[float] = None,
        request_timeout_sec: Optional[float] = None,
    ) -> None:
        configure_loop_wrapper_environment()
        configure_loop_wrapper_logging()
        if startup_timeout_sec is None:
            startup_timeout_sec = startup_timeout()
        if request_timeout_sec is None:
            request_timeout_sec = request_timeout()
        self.mode = mode or loop_backend()
        self.debug = McpSessionManager(
            mode=self.mode,
            xdebug_bin=xdebug_bin or default_xdebug_bin(),
            startup_timeout_sec=startup_timeout_sec,
            request_timeout_sec=request_timeout_sec,
            backend="xdebug",
            api_version="xdebug.v1",
            ready_protocol="xdebug-stdio-loop",
            target_key="fsdb",
            recovery_tool="debug.session.open",
        )
        self.cov = McpSessionManager(
            mode=self.mode,
            xdebug_bin=xcov_bin or default_xcov_bin(),
            startup_timeout_sec=startup_timeout_sec,
            request_timeout_sec=request_timeout_sec,
            backend="xcov",
            api_version="xcov.v1",
            ready_protocol="xcov-stdio-loop",
            target_key="vdb",
            recovery_tool="cov.session.open",
        )
        log_server_event("wrapper.service.init", True, launcher=self.mode)

    def dispatch(self, request: Json) -> Json:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if not isinstance(method, str) or not method:
            return {"id": req_id, **_error("INVALID_REQUEST", "request.method is required")}
        if not isinstance(params, dict):
            return {"id": req_id, **_error("INVALID_REQUEST", "request.params must be an object")}
        try:
            validate_method_params(method, params)
            result = self._dispatch_method(method, params)
        except TypeError as exc:
            return {"id": req_id, **_error("INVALID_PARAMS", str(exc))}
        except Exception as exc:
            return {"id": req_id, **_error("INTERNAL_ERROR", str(exc))}
        return _response(req_id, result)

    def _dispatch_method(self, method: str, params: Json) -> Any:
        if method == "server.ping":
            return {"ok": True, "pong": True, "mode": self.mode}
        if method == "debug.session.open":
            name = _required_str(params, "name")
            return self.debug.open_session(
                name=name,
                fsdb=params.get("fsdb"),
                daidir=params.get("daidir"),
                run_manifest=params.get("run_manifest"),
                queue=params.get("queue"),
                resource=params.get("resource"),
            )
        if method == "debug.session.list":
            return self.debug.list_sessions(
                include_tombstones=bool(params.get("include_tombstones", False)),
                verbose=bool(params.get("verbose", False)),
            )
        if method == "debug.session.doctor":
            return self.debug.doctor_session(
                _session_key(params), verbose=bool(params.get("verbose", False)))
        if method == "debug.session.close":
            return self.debug.close_session(_session_key(params))
        if method == "debug.session.kill":
            key = _session_key(params)
            if key == "all":
                return _error("INVALID_ARGUMENT", "all is not supported; provide one exact session")
            return self.debug.kill_session(key)
        if method == "debug.session.gc":
            return self.debug.gc_sessions(verbose=bool(params.get("verbose", False)))
        if method == "debug.query":
            action = _required_str(params, "action")
            if is_forbidden_native_session_action(action):
                return forbidden_native_session_error(action)
            return self.debug.query(
                session=_required_str(params, "session"),
                action=action,
                args=params.get("args") or {},
                limits=params.get("limits"),
                output_format=params.get("output_format", "xout"),
            )
        if method == "cov.session.open":
            return self.cov.open_session(
                name=_required_str(params, "name"),
                fsdb=_required_str(params, "vdb"),
                run_manifest=params.get("run_manifest"),
                queue=params.get("queue"),
                resource=params.get("resource"),
            )
        if method == "cov.session.list":
            return self.cov.list_sessions(
                include_tombstones=bool(params.get("include_tombstones", False)),
                verbose=bool(params.get("verbose", False)),
            )
        if method == "cov.session.doctor":
            return self.cov.doctor_session(
                _session_key(params), verbose=bool(params.get("verbose", False)))
        if method == "cov.session.close":
            return self.cov.close_session(_session_key(params))
        if method == "cov.session.kill":
            key = _session_key(params)
            if key == "all":
                return _error("INVALID_ARGUMENT", "all is not supported; provide one exact session")
            return self.cov.kill_session(key)
        if method == "cov.session.gc":
            return self.cov.gc_sessions(verbose=bool(params.get("verbose", False)))
        if method == "cov.query":
            action = _required_str(params, "action")
            if is_forbidden_native_session_action(action):
                return forbidden_native_session_error(action, backend="cov")
            return self.cov.query(
                session=_required_str(params, "session"),
                action=action,
                args=params.get("args") or {},
                limits=params.get("limits"),
                output=params.get("output"),
                output_format=params.get("output_format", "xout"),
            )
        return _error("UNKNOWN_METHOD", f"unsupported method: {method}")

    def close_all(self) -> None:
        self.debug.close_all()
        self.cov.close_all()


class LoopWrapperServer:
    def __init__(self, socket_path: str, service: Optional[LoopWrapperService] = None) -> None:
        self.socket_path = socket_path
        self.service = service or LoopWrapperService()
        self._stop = threading.Event()
        self._server_socket: Optional[socket.socket] = None
        self._threads: list[threading.Thread] = []
        self._created_socket = False
        self._ready = threading.Event()
        self._startup_finished = threading.Event()
        self._startup_error: Optional[BaseException] = None

    def wait_until_ready(self, timeout_sec: float) -> None:
        if not self._startup_finished.wait(timeout_sec):
            raise TimeoutError(
                f"loop wrapper server did not finish startup within {timeout_sec} seconds")
        if self._startup_error is not None:
            raise RuntimeError(
                f"loop wrapper server startup failed: {self._startup_error}") from self._startup_error
        if not self._ready.is_set():
            raise RuntimeError("loop wrapper server startup finished without becoming ready")

    def serve_forever(self) -> None:
        path = Path(self.socket_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if path.exists() or path.is_symlink():
                info = path.lstat()
                if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
                    raise RuntimeError("SOCKET_PATH_UNSAFE")
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(0.2)
                    probe.connect(self.socket_path)
                raise RuntimeError("SOCKET_PATH_UNSAFE")
        except ConnectionRefusedError:
            path.unlink()
        except FileNotFoundError:
            pass
        except Exception as exc:
            self._startup_error = exc
            self._startup_finished.set()
            raise
        log_uds_event("uds.listen.begin", True, socket_path=self.socket_path)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as srv:
            self._server_socket = srv
            try:
                srv.bind(self.socket_path)
                self._created_socket = True
                os.chmod(self.socket_path, 0o600)
                srv.listen()
                srv.settimeout(0.2)
            except Exception as exc:
                self._startup_error = exc
                self._startup_finished.set()
                raise
            self._ready.set()
            self._startup_finished.set()
            log_uds_event("uds.listen.ready", True, socket_path=self.socket_path)
            while not self._stop.is_set():
                try:
                    conn, _ = srv.accept()
                except socket.timeout:
                    continue
                except OSError as exc:
                    if self._stop.is_set():
                        break
                    log_uds_event("uds.accept.failed", False, error=str(exc))
                    continue
                log_uds_event("uds.accept", True)
                thread = threading.Thread(target=self._handle_client, args=(conn,), daemon=True)
                self._threads.append(thread)
                thread.start()
        self._shutdown_cleanup()

    def shutdown(self) -> None:
        self._stop.set()
        sock = self._server_socket
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def _handle_client(self, conn: socket.socket) -> None:
        with conn:
            reader = conn.makefile("r", encoding="utf-8")
            writer = conn.makefile("w", encoding="utf-8")
            for raw in reader:
                line = raw.strip()
                if not line:
                    continue
                t0 = time.monotonic()
                try:
                    request = json.loads(line)
                except Exception as exc:
                    log_uds_event("uds.request.invalid_json", False, error=str(exc), line=line[:1000])
                    self._write_response(writer, {"id": None, **_error("INVALID_JSON", str(exc))})
                    continue
                if not isinstance(request, dict):
                    rsp = {"id": None, **_error("INVALID_REQUEST", "request must be a JSON object")}
                    self._write_response(writer, rsp)
                    continue
                req_id = request.get("id")
                method = request.get("method")
                log_uds_event("uds.request.begin", True, request_id=req_id, method=method)
                if method == "server.shutdown":
                    log_uds_event("uds.shutdown.begin", True, request_id=req_id)
                    rsp = {"id": req_id, "ok": True, "result": {"ok": True, "shutdown": True}}
                    self._write_response(writer, rsp)
                    self.shutdown()
                    log_uds_event("uds.shutdown.end", True, request_id=req_id)
                    break
                rsp = self.service.dispatch(request)
                log_uds_event(
                    "uds.request.end",
                    bool(rsp.get("ok")),
                    request_id=req_id,
                    method=method,
                    elapsed_ms=int((time.monotonic() - t0) * 1000),
                )
                self._write_response(writer, rsp)

    def _write_response(self, writer: Any, response: Json) -> None:
        try:
            writer.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            writer.flush()
        except OSError as exc:
            log_uds_event("uds.response.write_failed", False, error=str(exc))

    def _shutdown_cleanup(self) -> None:
        self.service.close_all()
        if self._created_socket:
            try:
                Path(self.socket_path).unlink()
            except FileNotFoundError:
                pass


def send_requests(socket_path: str, requests: Iterable[Json], timeout_sec: float = 30.0) -> list[Json]:
    responses: list[Json] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_sec)
        sock.connect(socket_path)
        reader = sock.makefile("r", encoding="utf-8")
        writer = sock.makefile("w", encoding="utf-8")
        for req in requests:
            writer.write(json.dumps(req, ensure_ascii=False, separators=(",", ":")) + "\n")
            writer.flush()
            line = reader.readline()
            if not line:
                raise RuntimeError("loop wrapper server closed connection")
            responses.append(json.loads(line))
    return responses


def _required_str(params: Json, key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"missing required string param: {key}")
    return value


def _session_key(params: Json) -> str:
    value = params.get("session") or params.get("session_id") or params.get("name")
    if not isinstance(value, str) or not value:
        raise TypeError("missing required string param: session, session_id, or name")
    return value


def server_main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run the xverif SDK-free loop wrapper server")
    parser.add_argument("--socket", default=default_socket_path())
    parser.add_argument("--backend", choices=("direct", "lsf"), default=None)
    args = parser.parse_args(argv)
    if args.backend:
        os.environ["XVERIF_LOOP_BACKEND"] = args.backend
    server = LoopWrapperServer(args.socket)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


def client_main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Send JSONL requests to xverif-loop-server")
    parser.add_argument("--socket", default=default_socket_path())
    parser.add_argument("--json", help="single JSON request object")
    parser.add_argument("--timeout-sec", type=float, default=30.0)
    args = parser.parse_args(argv)
    if args.json:
        requests = [json.loads(args.json)]
    else:
        requests = [json.loads(line) for line in sys.stdin if line.strip()]
    for rsp in send_requests(args.socket, requests, timeout_sec=args.timeout_sec):
        print(json.dumps(rsp, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(server_main())
