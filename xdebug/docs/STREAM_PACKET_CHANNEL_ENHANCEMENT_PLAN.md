# stream packet fields and channel semantics enhancement plan

## Summary

This phase enhances existing `stream.*` packet semantics:

- Split packet data into `stable_fields` and `beat_fields`.
- Keep legacy `data` and `data_fields` compatible by treating them as beat fields.
- Make `channel_id` part of packet ownership semantics, not only row annotation.
- Support non-interleaved and interleaved packet reconstruction.
- Add `packet_at` query and `packet_beats` export.

The implementation remains JSON-only and does not migrate AXI/APB/list/interface
actions.

## Public Config

New recommended config shape:

```json
{
  "stable_fields": {
    "opcode": "top.req_opcode",
    "id": "top.req_id",
    "addr": "top.req_addr"
  },
  "beat_fields": {
    "data": "top.req_data",
    "mask": "top.req_mask"
  },
  "channel_id": "top.chid",
  "channel_id_valid": "every_beat",
  "allow_interleaving": false
}
```

Rules:

- `stable_fields` and `beat_fields` are optional maps of field name to stream
  expression.
- `data` and `data_fields` remain valid and are interpreted as legacy beat
  fields.
- Explicit `beat_fields` and legacy `data/data_fields` are merged; duplicate
  field names are errors.
- `stable_fields` and `beat_fields` must not share a field name.
- `channel_id_valid` values are `sop`, `eop`, and `every_beat`; default is
  `every_beat`.
- `allow_interleaving` defaults to false.
- `allow_interleaving=true` requires `channel_id`, sop/eop packet mode, and
  `channel_id_valid=every_beat`.
- `channel_id_valid=sop` and `channel_id_valid=eop` require sop/eop packet mode
  and are non-interleaved only.

## Packet Semantics

- `stable_fields` are sampled on each transfer beat and expected to remain
  constant inside a packet.
- A packet stores the first stable value as `stable_fields`.
- If a later beat changes a stable field, the packet records
  `stable_mismatches`; validate/query surfaces a warning.
- `beat_fields` are sampled on each transfer beat and kept as per-beat values.
- stream does not concatenate multi-beat data. Inline packet output shows a beat
  preview only.
- Packet beat preview uses the first 5 beats and last 5 beats. Packets with at
  most 10 beats can show all beats through those arrays without loss.
- Full beat values are exported through `stream.export kind=packet_beats` to an
  explicit caller-provided `output_file`.

## Channel Semantics

- `channel_id_valid=sop`: packet channel is sampled at the sop transfer.
- `channel_id_valid=eop`: packet channel is sampled at the eop transfer.
- `channel_id_valid=every_beat`: channel is sampled on every transfer.
- In non-interleaved mode, `every_beat` channel must remain constant within a
  packet; changes are errors because packet ownership is ambiguous.
- In interleaved mode, analyzer maintains `channel_id -> current packet` state
  and uses sop/eop within each channel to reconstruct packets.
- In interleaved mode, channel must be known on every transfer; unknown channel
  is an analysis error for packet reconstruction.

## Query and Export

Packet queries:

- `first_packet`
- `last_packet`
- `packet_at` with 0-based `packet_index`
- `packet_window`

Packet query shape:

- `first_packet`, `last_packet`, and `packet_at` return `found` and `packet`.
- `packet_at` returns `found:false` and `packet:null` when out of range.
- `packet_window` returns `packets`.
- All packet objects use the same schema: packet index, channel, time/cycle
  range, beat count, partial flags, stable fields, stable mismatches, and beat
  preview.

`match_field`:

- Add `field_scope`: `beat`, `stable`, or `any`; default `any`.
- `beat` returns transfer rows.
- `stable` returns packet objects.
- `any` may return both, each row annotated with match scope.

Exports:

- `kind=transfer`: transfer rows with stable/beat/channel columns.
- `kind=packet`: packet summaries with stable fields, first/last beat fields,
  channel, and mismatch indicator.
- `kind=packet_beats`: full beat table. This kind requires `output_file`.

## Implementation Steps

1. Extend `StreamConfig` and config JSON serialization/parsing.
2. Extend stream expression compilation to compile stable fields and beat fields
   separately.
3. Extend `StreamRow` and `StreamPacket` data structures with stable/beat/channel
   packet state.
4. Refactor analyzer packet construction:
   - single current packet for non-interleaved streams
   - per-channel current packet map for interleaved streams
   - stable mismatch tracking
   - beat preview generation
5. Extend `stream.query` for `packet_at` and `field_scope`.
6. Extend `stream.export` for `packet_beats` and updated transfer/packet files.
7. Update schema/examples/action inventory and docs.
8. Extend the real SV/FSDB fixture and pytest coverage.
9. Run build/schema/contract and real waveform pytest. License actions run
   outside the sandbox.
10. Commit with a detailed Chinese message and push to `origin/master`.

## Tests

- Legacy `data` and `data_fields` configs still pass.
- New `stable_fields` and `beat_fields` config passes.
- Duplicate stable/beat names produce validation errors.
- Stable fields that change within a packet produce mismatch records and warning.
- Beat fields show head/tail preview and export complete `packet_beats`.
- `first_packet`, `last_packet`, `packet_at`, and `packet_window` return expected
  packet objects.
- `packet_at` out of range returns `found:false`.
- `channel_id_valid=sop`, `eop`, and `every_beat` are each covered.
- Interleaved packets from two channels are reconstructed independently.
- Invalid interleaving configs produce validation errors.

Validation commands:

```sh
make -C xdebug -j4
make -C xdebug schema-test
make -C xdebug contract-test
/home/yian/miniconda3/bin/python -m pytest xdebug/tests/synthetic/test_stream_v1_real_waveform.py -q
```

