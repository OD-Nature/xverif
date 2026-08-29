# SDK-free Loop Wrapper Plan

## Goal

Add a Python Unix domain socket wrapper for stateful xverif backends.  The
wrapper is for environments that need LSF-backed `--stdio-loop` sessions but
cannot use MCP or cannot install the MCP SDK.

The first version covers only stateful `xdebug` and `xcov` operations:

- session open
- session query
- session list
- session close

It is not a replacement for all MCP tools.  Stateless tools such as `xbit`,
`xentry`, `xloc`, and `xsva` stay MCP-only or CLI-only for this rollout.
`xwiki` is maintained as a separate persistent-memory skill rather than a
loop-wrapper backend.

## Implementation Status

Completed in staged commits:

- Phase 0: `f7b7b16` added this plan before implementation.
- Phase 1: `288f446` added the SDK-free `xverif_loop` shared layer and kept
  existing `xverif_mcp` imports as compatibility wrappers.
- Phase 2: `5db8889` added `tools/xverif-loop-server`,
  `tools/xverif-loop-client`, UDS JSONL dispatch, and lifecycle tests.
- Phase 3: `f0dc2a1` added targeted wrapper logging regressions for direct
  logs, invalid JSON, redaction, fake LSF job detection, and cleanup.
- Phase 4: documentation and final validation were completed after Phase 3.

Validation evidence:

- `xverif_loop` import guard verifies the shared package has no MCP SDK import.
- UDS wrapper tests require running outside the restricted sandbox because the
  sandbox blocks Unix domain socket bind.
- Targeted wrapper and session tests passed with:
  `PYTHONPATH=<xverif-repo>/xverif_mcp/src pytest
  xverif_mcp/tests/test_loop_wrapper_uds.py
  xverif_mcp/tests/test_stdio_loop_session_lifecycle.py`.

## Phased Rollout

Each phase is committed and pushed separately.  The implementation must not
continue silently across phases without a clean local validation point.

### Phase 0: Planning Document

This document is the first phase.  It records scope, compatibility constraints,
protocol shape, logging requirements, and tests before implementation starts.

Validation:

- `git diff --check`

Commit and push:

- Commit only this document.
- Use a detailed Chinese commit message.
- Push the phase to the current upstream branch.

### Phase 1: SDK-free Shared Loop Layer

Create a shared Python package that does not import MCP.  The package should
live under the existing Python source root so both MCP and the new wrapper can
import it without installation.

Planned package:

- `xverif_mcp/src/xverif_loop/`

Move or mirror MCP-independent stateful backend code into this package:

- JSONL process protocol helpers
- direct and LSF launchers
- `bsub` command construction and fake LSF support
- loop-backed session object
- multi-session manager
- timeout and path configuration helpers
- structured NDJSON logging helpers

Compatibility rules:

- The shared package must not import `mcp` or `xverif_mcp.server`.
- Existing MCP tool names, parameter shapes, result shapes, and default
  `XVERIF_MCP_*` environment variables must remain compatible.
- Existing MCP logs continue to default to `~/.xverif/mcp`.
- `xverif_mcp` becomes a thin adapter over the shared layer.

Validation:

- Existing loop/session tests still pass.
- Add an import guard test proving `xverif_loop` is MCP SDK independent.

### Phase 2: UDS Wrapper Server and Client

Add two entrypoints:

- `tools/xverif-loop-server`
- `tools/xverif-loop-client`

The server listens on a Unix domain socket and accepts JSONL requests.  The
client connects to that socket and can send a single JSON request or a JSONL
stream from stdin.

Supported methods:

- `server.ping`
- `server.shutdown`
- `debug.session.open`
- `debug.session.list`
- `debug.session.close`
- `debug.query`
- `cov.session.open`
- `cov.session.list`
- `cov.session.close`
- `cov.query`

Request envelope:

```json
{"id":"1","method":"debug.session.open","params":{"name":"s0","fsdb":"wave.fsdb"}}
```

Success response:

```json
{"id":"1","ok":true,"result":{"ok":true,"session":{"alias":"s0"}}}
```

Error response:

```json
{"id":"1","ok":false,"error":{"code":"UNKNOWN_METHOD","message":"unsupported method"}}
```

Environment variables:

- `XVERIF_LOOP_BACKEND=direct|lsf`
- `XVERIF_LOOP_SOCKET`
- `XVERIF_LOOP_LOG_DIR`
- `XVERIF_LOOP_STARTUP_TIMEOUT_SEC`
- `XVERIF_LOOP_REQUEST_TIMEOUT_SEC`
- `XVERIF_LOOP_CLOSE_TIMEOUT_SEC`
- `XVERIF_LOOP_BKILL_TIMEOUT_SEC`

LSF command variables remain shared:

- `XVERIF_LSF_BSUB`
- `XVERIF_LSF_BKILL`
- `XVERIF_LSF_SESSION_QUEUE`
- `XVERIF_LSF_SESSION_RESOURCE`
- `XVERIF_MCP_FAKE_LSF=1` for existing fake LSF tests

Validation:

- UDS `server.ping`
- fake `xdebug` session open/query/close
- fake `xcov` session open/query/close
- invalid JSON
- unknown method
- missing required parameters
- backend crash and timeout

### Phase 3: Wrapper Logging and Targeted Tests

The wrapper gets its own log root while reusing the same structured NDJSON
style as MCP.

Default root:

- `~/.xverif/loop-wrapper`

Override:

- `XVERIF_LOOP_LOG_DIR`

Files:

- `logs/server.ndjson`
- `logs/uds.ndjson`
- `sessions/<alias>/session.ndjson`
- `sessions/<alias>/stdio.ndjson`
- `sessions/<alias>/lsf.ndjson`

Required common fields:

- `ts`
- `event_id`
- `pid`
- `layer`
- `component`
- `phase`
- `ok`
- `backend`
- `launcher`
- `request_id`
- `action`
- `session_id`
- `job_id`
- `job_name`
- `elapsed_ms`
- `error`
- `stderr_tail`

Required UDS phases:

- `uds.listen.begin`
- `uds.listen.ready`
- `uds.accept`
- `uds.request.begin`
- `uds.request.end`
- `uds.request.invalid_json`
- `uds.response.write_failed`
- `uds.shutdown.begin`
- `uds.shutdown.end`

Path redaction follows existing log policy:

- `XDEBUG_LOG_PATH_MODE=full|basename|hash`
- `XDEBUG_LOG_REDACT`

Validation:

- direct session open/query/close writes `uds`, `session`, and `stdio` logs
- fake LSF writes launcher, bsub, job id, and cleanup events
- invalid JSON, timeout, and backend crash write useful diagnostics
- basename/hash redaction does not leak full `fsdb`, `vdb`, `daidir`, or
  `socket_path`
- wrapper logs do not pollute stdout or stderr protocol streams

### Phase 4: Documentation Sync and Final Validation

Update user-facing docs after implementation and logging tests are in place:

- `xverif_mcp/README.md`
- `xdebug/README.md`
- `xdebug/help.txt` if the generated or checked-in help text is expected to
  mention the new wrapper
- this plan with final implementation status

Final validation:

- targeted shared-layer tests
- targeted UDS wrapper tests
- existing MCP session tests
- `git diff --check`

Final audit:

- shared package has no MCP SDK import
- MCP public interface remains compatible
- wrapper direct and fake LSF paths have test evidence
- wrapper logging has field and failure-mode regression evidence
- docs describe the supported stateful-only scope

## Implementation Defaults

- Use `xverif_loop` as the MCP-independent package name.
- Keep the existing session name validation rules.
- Use JSONL over UDS for both request and response streams.
- Handle one client connection per thread in the wrapper server.
- Serialize requests per backend session using the existing per-session lock.
- Close all live sessions during server shutdown.
- Unlink the socket path during shutdown when the server created it.
