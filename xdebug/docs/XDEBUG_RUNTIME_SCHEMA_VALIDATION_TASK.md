# xdebug Runtime Schema Validation Task

## Objective

Implement runtime request validation for xdebug actions using the checked-in action request schemas as the source of truth.

The runtime validator must prevent malformed AI/tool inputs from reaching action handlers. It should return actionable `INVALID_REQUEST` errors that identify the wrong argument path, expected shape, received type, relevant allowed values, schema path, and an example when available.

## Decisions

- Use `pboettch/json-schema-validator` as the embedded JSON Schema validator.
- Treat runtime validation as draft-7 validation.
- Keep checked-in schemas as they are declared today; load schemas into memory and convert `$schema` to draft-7 only for runtime compilation.
- Enable validation for all registered actions, not only selected actions.
- Tighten request schemas so unknown top-level request fields and unknown `args` fields are rejected.
- Do not replace semantic handler checks. Handlers still validate signal existence, time parsing semantics, begin/end relationships, FSDB/NPI failures, protocol semantics, and runtime resource state.

## Implementation Requirements

### Dependency

- Vendor the minimal runtime files from `pboettch/json-schema-validator` under `xdebug/third_party/json-schema-validator/`.
- Preserve the upstream MIT license file in the vendored directory.
- Do not vendor upstream tests, examples, or unrelated assets.
- Wire the validator into `xdebug/Makefile` for both the public xdebug executable and internal engine executable.

### Runtime Validator

- Add a reusable C++ validator component that:
  - maps an action to `schemas/v1/actions/<action>.request.schema.json`;
  - loads and caches compiled validators;
  - converts only the in-memory `$schema` value to `http://json-schema.org/draft-07/schema#`;
  - disallows network schema loading;
  - allows in-document refs and repo-local refs only if needed;
  - accepts `nlohmann::ordered_json` request objects and validates the full request envelope.
- Convert validation failures to xdebug-style JSON errors:
  - `error.code = INVALID_REQUEST`;
  - `error.message` is concise and readable;
  - `error.recoverable = true`;
  - `data.invalid_arg` uses an AI-friendly path such as `args.checks[0]`;
  - `data.expected`, `data.received_type`, `data.allowed_values`, `data.schema_path`, and `data.example` are filled when derivable;
  - `summary.invalid_arg` and `summary.message` mirror the key diagnosis.

### Entry Points

- Public path:
  - call runtime schema validation in `Dispatcher::dispatch_impl()` after action lookup and before resource resolution or handler dispatch.
  - cover CLI JSON, stdio-loop, MCP, and normal public action dispatch.
- Internal engine path:
  - call the same validator in engine server request handling before `EngineActionHandler::run()`.
  - accept `xdebug.internal.v1` by adapting the internal request envelope to the public action schema during validation, without changing the actual request sent to the handler.
- Batch:
  - validate the batch request itself first;
  - keep child request validation through recursive dispatch;
  - preserve existing `continue_on_error` and `stop_on_error` behavior.

### Schema Tightening

- Use `xdebug/specs/actions/actions.yaml` and existing request schemas as the maintenance source for strict request schemas.
- Add or extend a schema maintenance script so strict schema changes are reproducible.
- For all action request schemas:
  - set top-level `additionalProperties` to `false`;
  - allow only `api_version`, `request_id`, `action`, `target`, `args`, `limits`, and `output` at the top level, unless an action has a documented exception;
  - set `args.additionalProperties` to `false`;
  - keep only fields actually supported by that action under `args.properties`;
  - preserve documented `required`, `enum`, `oneOf`, `anyOf`, `allOf`, `if/then`, `const`, `items`, and nested object rules.
- Ensure these known complex action shapes remain valid:
  - `detect_abnormal.args.checks[]`;
  - `event.find` and `event.export` expression, alias, and clock forms;
  - `value.batch_at` signal/time forms;
  - `stream.*` config/query/export forms;
  - `batch.args.requests[]`;
  - `session.open`, `session.close`, `session.kill`, and `session.doctor` target/session-id forms.

## Acceptance Criteria

- Every registered non-removed action has a request schema that the runtime validator can compile.
- Existing checked-in request examples pass strict runtime validation.
- Unknown top-level request fields are rejected.
- Unknown `args` fields are rejected for all actions.
- Type errors, enum errors, missing required fields, bad array item shape, and conditional schema failures return `INVALID_REQUEST` before handler execution.
- `detect_abnormal` rejects `checks: ["unknown_xz"]` with an actionable path such as `args.checks[0]`.
- A validation failure does not kill or corrupt an existing session.
- `schema` action still returns the checked-in schema, not the in-memory draft-7 converted copy.
- Existing semantic errors still come from handlers where appropriate.

## Test Plan

- Unit tests:
  - validator loads a 2020-12-declared request schema and validates it as draft-7 in memory;
  - required, type, enum, items, `additionalProperties`, `oneOf`, and `if/then/const` failures produce stable error data;
  - internal `xdebug.internal.v1` requests validate against public schemas without changing handler input.
- Contract tests:
  - all action request schemas compile under the runtime validator;
  - all request examples pass strict validation;
  - negative fixtures cover unknown top-level field, unknown `args` field, bad enum, bad array item, and missing required field.
- Runtime tests:
  - public CLI request with invalid `detect_abnormal.checks[0]` returns `INVALID_REQUEST`;
  - direct session/socket request with the same bad input returns `INVALID_REQUEST`;
  - `batch` child invalid input is reported inside that child result;
  - session remains healthy after validation failure.
- Required validation commands:
  - `make -C xdebug schema-test`;
  - `make -C xdebug unit-test`;
  - `make -C xdebug all`;
  - `make -C xdebug contract-test`;
  - `python3 xdebug/tests/waveform/run_complex_wave.py --xdebug xdebug/xdebug --mode nonaxi --skip-build`.

## Constraints

- NPI, VCS, FSDB, session, MCP, and waveform runtime tests must be run outside the sandbox.
- Do not introduce a second hand-written action argument spec that duplicates JSON Schema.
- Do not silently fall back to handler-only validation when schema compilation fails; fail clearly with a configuration/runtime validation error.
- Do not loosen `detect_abnormal.checks` to support string shorthand.
