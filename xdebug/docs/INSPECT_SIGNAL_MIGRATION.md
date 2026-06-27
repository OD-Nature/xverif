# inspect_signal migration

`inspect_signal` has been removed from the public action catalog.

Use these stable actions instead:

- Point value lookup: `value.at`
- Value-change timeline: `signal.changes`
- Sampled activity and cycle counts: `signal.statistics`
- Glitch, stuck, and unknown-value checks: `detect_anomaly`

Calls to `inspect_signal` should be migrated instead of routed through a compatibility alias.
