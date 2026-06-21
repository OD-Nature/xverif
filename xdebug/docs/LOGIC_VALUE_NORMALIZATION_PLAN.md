# xdebug Logic Value Normalization Plan

## Summary

- Add an xdebug-owned logic value normalization layer. NPI remains the source of
  raw FSDB values only; action, JSON, XOUT, and MCP-facing code should not depend
  on NPI value classes.
- Render user-visible values as SystemVerilog literals. Use `<width>'h<value>`
  when width is reliable, and `'h<value>` when width is unknown. Do not use `0x`
  as xdebug's default value format.
- Reject `0x...` and `0X...` in xdebug JSON request value literals. Return a
  format error instead of silently converting.
- Preserve compact response shapes where they currently return maps of strings;
  normalize the string content rather than changing those maps into objects.

## Public Interface Changes

- JSON response value strings are normalized to SV literal style:
  - known with reliable width: `32'h4000000c`
  - known without reliable width: `'h22`
  - unknown with reliable width: `8'hxz`
- Full value objects keep `{value, known}` and may add `width`, `bits`, `has_x`,
  and `has_z`.
- XOUT continues to hide `known:true` and compact known value objects to
  `<width>'h...` or `'h...`.
- JSON request fields that represent expected values or match/filter literals
  must not use `0x...`. Accepted forms are SV literals such as `32'h22`, `'h22`,
  `'b1010`, `'d34`, or plain decimal.
- Invalid user value literals return `VALUE_FORMAT_INVALID` with a message that
  says `0x` is not accepted and suggests an SV literal.

## Implementation Changes

- Add `xdebug/src/waveform/value/logic_value.{h,cpp}`.
- Provide two parse modes:
  - FSDB/raw mode accepts NPI-returned values and legacy raw hex bodies.
  - User-literal mode rejects `0x...` and validates JSON request literals.
- Replace scattered `contains_xz`, `make_value_object`, and numeric comparison
  logic in waveform actions with the shared helper.
- Keep `StreamValue` as the stream expression internal representation, but emit
  its JSON and export-facing value text through the shared normalization rules.
- Do not force aggregate FSDB array values into bit vectors; keep existing
  indexed aggregate behavior and normalize scalar element values separately when
  needed.

## Test Plan

- Unit-test raw FSDB normalization, user literal parsing, X/Z diagnostics, width
  handling, and `0x...` rejection.
- Update XOUT/value tests to expect SV literal output.
- Update stream synthetic JSON assertions from `0x...` to SV literals.
- Add request-level coverage that `verify.conditions` and stream match/filter
  values reject `0x...` with `VALUE_FORMAT_INVALID`.
- Run focused unit/contract tests first, then `schema-test`, `unit-test`, and
  `contract-test`. FSDB/NPI-backed tests must run outside the sandbox.
