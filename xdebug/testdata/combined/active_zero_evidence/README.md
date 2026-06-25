# Active trace zero-evidence fixture

This fixture captures cases where the design signal has a real source, but
native active trace does not provide assignment evidence for the queried point.

The fixture is intentionally not an undriven-net test.  It covers:

- a module output driven by a single `bufif1` primitive, where
  `trace.active_driver_chain` must not turn no data dependency into
  `primary_input`;
- an `output reg` driven by `sample_flag <= sample_flag_expr`, where
  `sample_flag_expr` is `|sample_vec_q`, matching the reduction-OR shape
  that can produce native zero-result evidence for the output flop.
- a direct query on a child module input port connected to a parent signal,
  which must follow the parent connection instead of stopping as
  `primary_input`;
- a real top-level input port with no parent connection, which is still allowed
  to terminate as `primary_input`;
- a matrix of `output reg q <= cb_expr` cases where `cb_expr` is a reduction,
  bitwise/logical expression, comparison, select, part-select, concat, or nested
  expression. These capture native zero-result evidence on ordinary module
  outputs with real expression drivers.
