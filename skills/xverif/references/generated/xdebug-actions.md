# xdebug 全量 Action 索引

本文件由 `skills/xverif/scripts/generate_references.py` 从 canonical action specs 生成。
用途是保证所有能力可发现；精确参数以 runtime catalog、action-specific schema 和 checked-in example 为准。

| Action | Category | Requires | Required inputs | Request schema | Example |
| --- | --- | --- | --- | --- | --- |
| `actions` | builtin | none | 以 action schema 为准 | `xdebug/schemas/v1/actions/actions.request.schema.json` | `xdebug/examples/requests/actions.basic.json` |
| `apb.config.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/apb.config.list.request.schema.json` | `xdebug/examples/requests/apb.config.list.basic.json` |
| `apb.config.load` | waveform | waveform | name, one of config, one of config_path | `xdebug/schemas/v1/actions/apb.config.load.request.schema.json` | `xdebug/examples/requests/apb.config.load.basic.json` |
| `apb.cursor` | waveform | waveform | name, op | `xdebug/schemas/v1/actions/apb.cursor.request.schema.json` | `xdebug/examples/requests/apb.cursor.basic.json` |
| `apb.query` | waveform | waveform | name | `xdebug/schemas/v1/actions/apb.query.request.schema.json` | `xdebug/examples/requests/apb.query.basic.json` |
| `apb.transfer_window` | waveform | waveform | name | `xdebug/schemas/v1/actions/apb.transfer_window.request.schema.json` | `xdebug/examples/requests/apb.transfer_window.basic.json` |
| `axi.analysis` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.analysis.request.schema.json` | `xdebug/examples/requests/axi.analysis.basic.json` |
| `axi.export` | waveform | waveform | name, one of time_range | `xdebug/schemas/v1/actions/axi.export.request.schema.json` | `xdebug/examples/requests/axi.export.basic.json` |
| `axi.channel_stall` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.channel_stall.request.schema.json` | `xdebug/examples/requests/axi.channel_stall.basic.json` |
| `axi.config.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/axi.config.list.request.schema.json` | `xdebug/examples/requests/axi.config.list.basic.json` |
| `axi.config.load` | waveform | waveform | name, one of config, one of config_path | `xdebug/schemas/v1/actions/axi.config.load.request.schema.json` | `xdebug/examples/requests/axi.config.load.basic.json` |
| `axi.cursor` | waveform | waveform | name, op | `xdebug/schemas/v1/actions/axi.cursor.request.schema.json` | `xdebug/examples/requests/axi.cursor.basic.json` |
| `axi.latency_outlier` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.latency_outlier.request.schema.json` | `xdebug/examples/requests/axi.latency_outlier.basic.json` |
| `axi.outstanding_timeline` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.outstanding_timeline.request.schema.json` | `xdebug/examples/requests/axi.outstanding_timeline.basic.json` |
| `axi.query` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.query.request.schema.json` | `xdebug/examples/requests/axi.query.basic.json` |
| `axi.request_response_pair` | waveform | waveform | name | `xdebug/schemas/v1/actions/axi.request_response_pair.request.schema.json` | `xdebug/examples/requests/axi.request_response_pair.basic.json` |
| `batch` | builtin | none | requests | `xdebug/schemas/v1/actions/batch.request.schema.json` | `xdebug/examples/requests/batch.basic.json` |
| `counter.statistics` | waveform | waveform | clock, time_range, vld, cnt | `xdebug/schemas/v1/actions/counter.statistics.request.schema.json` | `xdebug/examples/requests/counter.statistics.basic.json` |
| `cursor.delete` | waveform | waveform | name | `xdebug/schemas/v1/actions/cursor.delete.request.schema.json` | `xdebug/examples/requests/cursor.delete.basic.json` |
| `cursor.get` | waveform | waveform | name | `xdebug/schemas/v1/actions/cursor.get.request.schema.json` | `xdebug/examples/requests/cursor.get.basic.json` |
| `cursor.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/cursor.list.request.schema.json` | `xdebug/examples/requests/cursor.list.basic.json` |
| `cursor.set` | waveform | waveform | name, time | `xdebug/schemas/v1/actions/cursor.set.request.schema.json` | `xdebug/examples/requests/cursor.set.basic.json` |
| `cursor.use` | waveform | waveform | name | `xdebug/schemas/v1/actions/cursor.use.request.schema.json` | `xdebug/examples/requests/cursor.use.basic.json` |
| `detect_abnormal` | waveform | waveform | signals | `xdebug/schemas/v1/actions/detect_abnormal.request.schema.json` | `xdebug/examples/requests/detect_abnormal.basic.json` |
| `event.config.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/event.config.list.request.schema.json` | `xdebug/examples/requests/event.config.list.basic.json` |
| `event.config.load` | waveform | waveform | name | `xdebug/schemas/v1/actions/event.config.load.request.schema.json` | `xdebug/examples/requests/event.config.load.basic.json` |
| `event.export` | waveform | waveform | expr, one of name, one of clock/signals | `xdebug/schemas/v1/actions/event.export.request.schema.json` | `xdebug/examples/requests/event.export.basic.json` |
| `event.find` | waveform | waveform | expr, one of name, one of clock/signals | `xdebug/schemas/v1/actions/event.find.request.schema.json` | `xdebug/examples/requests/event.find.basic.json` |
| `expr.eval_at` | waveform | waveform | expr, time, signals, clock | `xdebug/schemas/v1/actions/expr.eval_at.request.schema.json` | `xdebug/examples/requests/expr.eval_at.basic.json` |
| `expr.normalize` | design | none | expr | `xdebug/schemas/v1/actions/expr.normalize.request.schema.json` | `xdebug/examples/requests/expr.normalize.basic.json` |
| `handshake.inspect` | waveform | waveform | clock, valid, ready | `xdebug/schemas/v1/actions/handshake.inspect.request.schema.json` | `xdebug/examples/requests/handshake.inspect.basic.json` |
| `list.add` | waveform | waveform | name, signal | `xdebug/schemas/v1/actions/list.add.request.schema.json` | `xdebug/examples/requests/list.add.basic.json` |
| `list.create` | waveform | waveform | name | `xdebug/schemas/v1/actions/list.create.request.schema.json` | `xdebug/examples/requests/list.create.basic.json` |
| `list.delete` | waveform | waveform | name, one of signal, one of index | `xdebug/schemas/v1/actions/list.delete.request.schema.json` | `xdebug/examples/requests/list.delete.basic.json` |
| `list.diff` | waveform | waveform | name, time_range | `xdebug/schemas/v1/actions/list.diff.request.schema.json` | `xdebug/examples/requests/list.diff.basic.json` |
| `list.export` | waveform | waveform | name | `xdebug/schemas/v1/actions/list.export.request.schema.json` | `xdebug/examples/requests/list.export.basic.json` |
| `list.show` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/list.show.request.schema.json` | `xdebug/examples/requests/list.show.basic.json` |
| `list.validate` | waveform | waveform | name | `xdebug/schemas/v1/actions/list.validate.request.schema.json` | `xdebug/examples/requests/list.validate.basic.json` |
| `list.value_at` | waveform | waveform | name, time, clock | `xdebug/schemas/v1/actions/list.value_at.request.schema.json` | `xdebug/examples/requests/list.value_at.basic.json` |
| `sampled_pulse.inspect` | waveform | waveform | clock, valid | `xdebug/schemas/v1/actions/sampled_pulse.inspect.request.schema.json` | `xdebug/examples/requests/sampled_pulse.inspect.basic.json` |
| `schema` | builtin | none | 以 action schema 为准 | `xdebug/schemas/v1/actions/schema.request.schema.json` | `xdebug/examples/requests/schema.basic.json` |
| `scope.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/scope.list.request.schema.json` | `xdebug/examples/requests/scope.list.basic.json` |
| `scope.roots` | waveform | any | 以 action schema 为准 | `xdebug/schemas/v1/actions/scope.roots.request.schema.json` | `xdebug/examples/requests/scope.roots.basic.json` |
| `session.close` | session | session | 以 action schema 为准 | `xdebug/schemas/v1/actions/session.close.request.schema.json` | `xdebug/examples/requests/session.close.basic.json` |
| `session.doctor` | session | session | 以 action schema 为准 | `xdebug/schemas/v1/actions/session.doctor.request.schema.json` | `xdebug/examples/requests/session.doctor.basic.json` |
| `session.gc` | session | none | 以 action schema 为准 | `xdebug/schemas/v1/actions/session.gc.request.schema.json` | `xdebug/examples/requests/session.gc.basic.json` |
| `session.kill` | session | session | 以 action schema 为准 | `xdebug/schemas/v1/actions/session.kill.request.schema.json` | `xdebug/examples/requests/session.kill.basic.json` |
| `session.list` | session | session | 以 action schema 为准 | `xdebug/schemas/v1/actions/session.list.request.schema.json` | `xdebug/examples/requests/session.list.basic.json` |
| `session.open` | session | any | name | `xdebug/schemas/v1/actions/session.open.request.schema.json` | `xdebug/examples/requests/session.open.basic.json` |
| `signal.canonicalize` | design | design | signal | `xdebug/schemas/v1/actions/signal.canonicalize.request.schema.json` | `xdebug/examples/requests/signal.canonicalize.basic.json` |
| `signal.changes` | waveform | waveform | signal | `xdebug/schemas/v1/actions/signal.changes.request.schema.json` | `xdebug/examples/requests/signal.changes.basic.json` |
| `signal.resolve` | design | design | signal | `xdebug/schemas/v1/actions/signal.resolve.request.schema.json` | `xdebug/examples/requests/signal.resolve.basic.json` |
| `signal.stability` | waveform | waveform | signal | `xdebug/schemas/v1/actions/signal.stability.request.schema.json` | `xdebug/examples/requests/signal.stability.basic.json` |
| `signal.statistics` | waveform | waveform | signal | `xdebug/schemas/v1/actions/signal.statistics.request.schema.json` | `xdebug/examples/requests/signal.statistics.basic.json` |
| `source.context` | design | none | file, line | `xdebug/schemas/v1/actions/source.context.request.schema.json` | `xdebug/examples/requests/source.context.basic.json` |
| `trace.active_driver` | combined | combined | signal, time | `xdebug/schemas/v1/actions/trace.active_driver.request.schema.json` | `xdebug/examples/requests/trace.active_driver.basic.json` |
| `trace.active_driver_chain` | combined | combined | signal, time | `xdebug/schemas/v1/actions/trace.active_driver_chain.request.schema.json` | `xdebug/examples/requests/trace.active_driver_chain.basic.json` |
| `trace.driver` | design | design | signal | `xdebug/schemas/v1/actions/trace.driver.request.schema.json` | `xdebug/examples/requests/trace.driver.basic.json` |
| `trace.load` | design | design | signal | `xdebug/schemas/v1/actions/trace.load.request.schema.json` | `xdebug/examples/requests/trace.load.basic.json` |
| `rc.generate` | waveform | waveform | config_path, output | `xdebug/schemas/v1/actions/rc.generate.request.schema.json` | `xdebug/examples/requests/rc.generate.basic.json` |
| `value.at` | waveform | waveform | signal, time, clock | `xdebug/schemas/v1/actions/value.at.request.schema.json` | `xdebug/examples/requests/value.at.basic.json` |
| `value.batch_at` | waveform | waveform | signals, time, clock | `xdebug/schemas/v1/actions/value.batch_at.request.schema.json` | `xdebug/examples/requests/value.batch_at.basic.json` |
| `verify.conditions` | waveform | waveform | conditions, time, clock, signals | `xdebug/schemas/v1/actions/verify.conditions.request.schema.json` | `xdebug/examples/requests/verify.conditions.basic.json` |
| `window.verify` | waveform | waveform | clock, conditions, signals | `xdebug/schemas/v1/actions/window.verify.request.schema.json` | `xdebug/examples/requests/window.verify.basic.json` |
| `stream.config.load` | waveform | waveform | one of streams, one of config, one of config_path, one of file | `xdebug/schemas/v1/actions/stream.config.load.request.schema.json` | `xdebug/examples/requests/stream.config.load.basic.json` |
| `stream.config.list` | waveform | waveform | 以 action schema 为准 | `xdebug/schemas/v1/actions/stream.config.list.request.schema.json` | `xdebug/examples/requests/stream.config.list.basic.json` |
| `stream.show` | waveform | waveform | stream | `xdebug/schemas/v1/actions/stream.show.request.schema.json` | `xdebug/examples/requests/stream.show.basic.json` |
| `stream.validate` | waveform | waveform | stream | `xdebug/schemas/v1/actions/stream.validate.request.schema.json` | `xdebug/examples/requests/stream.validate.basic.json` |
| `stream.query` | waveform | waveform | stream, query | `xdebug/schemas/v1/actions/stream.query.request.schema.json` | `xdebug/examples/requests/stream.query.basic.json` |
| `stream.export` | waveform | waveform | stream | `xdebug/schemas/v1/actions/stream.export.request.schema.json` | `xdebug/examples/requests/stream.export.basic.json` |
| `signal.search` | design | design | 以 action schema 为准 | `-` | `-` |

共 71 个 action。主流程见 [xdebug capability](../capabilities/xdebug.md)。
