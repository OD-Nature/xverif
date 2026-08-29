# xdebug 当前 Action XOUT 完整输出 (2026-06-30)

> 参考: `<xring-repo>/dv/doc/feedback/2026-06-27-v29-xdebug-full-xout-complete.md`
> daidir=`<xring-repo>/dv/run/out/sanity/build/simv.daidir`
> fsdb=`<xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb`
> 已跳过参考文件中的已删除 action；本文件由当前 xdebug 二进制重放生成。
> regenerated_session=`xout_current_20260630_regen`
> regenerated_at=`2026-06-30T14:01:45`


## actions

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "actions"
}
```

xout rc=0:
```text
@xdebug.actions.v1
summary:
  action_count : 70
  removed_count: 1

implemented:
  actions
  apb.config.list
  apb.config.load
  apb.cursor
  apb.query
  apb.transfer_window
  axi.analysis
  axi.channel_stall
  axi.config.list
  axi.config.load
  axi.cursor
  axi.export
  axi.latency_outlier
  axi.outstanding_timeline
  axi.query
  axi.request_response_pair
  batch
  counter.statistics
  cursor.delete
  cursor.get

actions:
  name                       category  status        requires  request_schema                                                    response_schema                                                    handler_kind
  actions                    builtin   stable        none      schemas/v1/actions/actions.request.schema.json                    schemas/v1/actions/actions.response.schema.json                    actions
  apb.config.list            waveform  stable        waveform  schemas/v1/actions/apb.config.list.request.schema.json            schemas/v1/actions/apb.config.list.response.schema.json            engine_forward
  apb.config.load            waveform  stable        waveform  schemas/v1/actions/apb.config.load.request.schema.json            schemas/v1/actions/apb.config.load.response.schema.json            engine_forward
  apb.cursor                 waveform  stable        waveform  schemas/v1/actions/apb.cursor.request.schema.json                 schemas/v1/actions/apb.cursor.response.schema.json                 engine_forward
  apb.query                  waveform  stable        waveform  schemas/v1/actions/apb.query.request.schema.json                  schemas/v1/actions/apb.query.response.schema.json                  engine_forward
  apb.transfer_window        waveform  experimental  waveform  schemas/v1/actions/apb.transfer_window.request.schema.json        schemas/v1/actions/apb.transfer_window.response.schema.json        engine_forward
  axi.analysis               waveform  stable        waveform  schemas/v1/actions/axi.analysis.request.schema.json               schemas/v1/actions/axi.analysis.response.schema.json               engine_forward
  axi.channel_stall          waveform  experimental  waveform  schemas/v1/actions/axi.channel_stall.request.schema.json          schemas/v1/actions/axi.channel_stall.response.schema.json          engine_forward
  axi.config.list            waveform  stable        waveform  schemas/v1/actions/axi.config.list.request.schema.json            schemas/v1/actions/axi.config.list.response.schema.json            engine_forward
  axi.config.load            waveform  stable        waveform  schemas/v1/actions/axi.config.load.request.schema.json            schemas/v1/actions/axi.config.load.response.schema.json            engine_forward
  axi.cursor                 waveform  stable        waveform  schemas/v1/actions/axi.cursor.request.schema.json                 schemas/v1/actions/axi.cursor.response.schema.json                 engine_forward
  axi.export                 waveform  stable        waveform  schemas/v1/actions/axi.export.request.schema.json                 schemas/v1/actions/axi.export.response.schema.json                 engine_forward
  axi.latency_outlier        waveform  experimental  waveform  schemas/v1/actions/axi.latency_outlier.request.schema.json        schemas/v1/actions/axi.latency_outlier.response.schema.json        engine_forward
  axi.outstanding_timeline   waveform  experimental  waveform  schemas/v1/actions/axi.outstanding_timeline.request.schema.json   schemas/v1/actions/axi.outstanding_timeline.response.schema.json   engine_forward
  axi.query                  waveform  stable        waveform  schemas/v1/actions/axi.query.request.schema.json                  schemas/v1/actions/axi.query.response.schema.json                  engine_forward
  axi.request_response_pair  waveform  experimental  waveform  schemas/v1/actions/axi.request_response_pair.request.schema.json  schemas/v1/actions/axi.request_response_pair.response.schema.json  engine_forward
  batch                      builtin   stable        none      schemas/v1/actions/batch.request.schema.json                      schemas/v1/actions/batch.response.schema.json                      batch
  counter.statistics         waveform  stable        waveform  schemas/v1/actions/counter.statistics.request.schema.json         schemas/v1/actions/counter.statistics.response.schema.json         engine_forward
  cursor.delete              waveform  stable        waveform  schemas/v1/actions/cursor.delete.request.schema.json              schemas/v1/actions/cursor.delete.response.schema.json              engine_forward
  cursor.get                 waveform  stable        waveform  schemas/v1/actions/cursor.get.request.schema.json                 schemas/v1/actions/cursor.get.response.schema.json                 engine_forward

removed:
  signal.search

design:
  expr.normalize
  signal.canonicalize
  signal.resolve
  source.context
  trace.driver
  trace.load

waveform:
  apb.config.list
  apb.config.load
  apb.cursor
  apb.query
  apb.transfer_window
  axi.analysis
  axi.channel_stall
  axi.config.list
  axi.config.load
  axi.cursor
  axi.export
  axi.latency_outlier
  axi.outstanding_timeline
  axi.query
  axi.request_response_pair
  counter.statistics
  cursor.delete
  cursor.get
  cursor.list
  cursor.set

combined:
  trace.active_driver
  trace.active_driver_chain

builtin:
  actions
  batch
  schema

session:
  session.close
  session.doctor
  session.gc
  session.kill
  session.list
  session.open
```

## schema

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "schema",
  "args": {
    "action": "trace.driver",
    "kind": "response"
  }
}
```

xout rc=0:
```text
@xdebug.schema.v1
summary:
  action     : trace.driver
  kind       : response
  schema_path: schemas/v1/actions/trace.driver.response.schema.json
  ai_hint    : Read schema_path JSON file or use --json for full schema.
```

## session.open

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "session.open",
  "target": {
    "daidir": "<xring-repo>/dv/run/out/sanity/build/simv.daidir",
    "fsdb": "<xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb"
  },
  "args": {
    "name": "xout_current_20260630_regen"
  }
}
```

xout rc=0:
```text
@xdebug.session.open.v1
summary:
  session_id: xout_current_20260630_regen
  mode      : combined

session:
  id         : xout_current_20260630_regen
  session_id : xout_current_20260630_regen
  mode       : combined
  daidir     : <xring-repo>/dv/run/out/sanity/build/simv.daidir
  fsdb       : <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb
  socket_path: ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/socket
  transport  : uds
  file_dir   : ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/transport
  server_host: localhost.localdomain
```

## session.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "session.list"
}
```

xout rc=0:
```text
@xdebug.session.list.v1
summary:
  session_count        : 8
  expired_removed_count: 0

sessions:
  id                                session_id                        mode      daidir                                                                          fsdb                                                                           socket_path                                                                  transport  file_dir                                                                        server_host            server_pid  created_at  last_active  dbdir_mtime  dbdir_size  dbdir_dev  dbdir_inode  fsdb_mtime  fsdb_size  fsdb_dev  fsdb_inode
  xout_current_20260630             xout_current_20260630             combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_f68723fc1c2acbb9/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_f68723fc1c2acbb9/transport  localhost.localdomain  2879498     1782790678  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_b           xout_current_20260630_b           combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_09750ab00d736010/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_09750ab00d736010/transport  localhost.localdomain  2881701     1782790854  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_c           xout_current_20260630_c           combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_09750bb00d7361c3/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_09750bb00d7361c3/transport  localhost.localdomain  2883339     1782790963  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  active_driver_py_2918664          active_driver_py_2918664          combined  <xverif-repo>/xdebug/testdata/combined/active_driver/out/simv.daidir        <xverif-repo>/xdebug/testdata/combined/active_driver/out/waves.fsdb        ~/.xdebug/engine/sessions/active_driver_py_02e879d9c249d84d/socket  uds        ~/.xdebug/engine/sessions/active_driver_py_02e879d9c249d84d/transport  localhost.localdomain  2918683     1782796007  1782796130   1782715423   4096        66307      554070230    1782715423  9821       66307     1611510105
  if_port_root_py_2918664           if_port_root_py_2918664           combined  <xverif-repo>/xdebug/testdata/combined/interface_port_root/out/simv.daidir  <xverif-repo>/xdebug/testdata/combined/interface_port_root/out/waves.fsdb  ~/.xdebug/engine/sessions/if_port_root_py__1634e14c3170c8f0/socket  uds        ~/.xdebug/engine/sessions/if_port_root_py__1634e14c3170c8f0/transport  localhost.localdomain  2918741     1782796007  1782796130   1781511675   4096        66307      541233024    1781579586  9741       66307     1087379363
  xout_current_20260630_envtrace    xout_current_20260630_envtrace    combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_d4611ca55364fffe/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_d4611ca55364fffe/transport  localhost.localdomain  2921617     1782796126  1782799070   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_limitcheck  xout_current_20260630_limitcheck  combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_2d8694d322bf7e53/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_2d8694d322bf7e53/transport  localhost.localdomain  2940979     1782799143  1782799170   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_regen       xout_current_20260630_regen       combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/transport  localhost.localdomain  2941852     1782799307  1782799307   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
```

## session.doctor

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "session.doctor",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=0:
```text
@xdebug.session.doctor.v1
summary:
  session_id: xout_current_20260630_regen
  mode      : combined
  healthy   : true

health:
  api_version: xdebug.v1
  ok         : true
  action     : session.doctor

tool:
  name   : xdebug
  version: 0.1.0

session:
  id         : xout_current_20260630_regen
  session_id : xout_current_20260630_regen
  dbdir      : <xring-repo>/dv/run/out/sanity/build/simv.daidir
  dbdir_path : <xring-repo>/dv/run/out/sanity/build/simv.daidir
  design_file: <xring-repo>/dv/run/out/sanity/build/simv.daidir
  fsdb       : <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb
  fsdb_file  : <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb
  pid        : 2941852
  transport  : uds
  socket_path: ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/socket
  file_dir   : ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/transport
  port       : 0
  server_host: localhost.localdomain
  created_at : 1782799307
  last_active: 1782799307
  dbdir_mtime: 1781509284
  dbdir_size : 4096
  dbdir_dev  : 66307
  dbdir_inode: 3553032
  fsdb_mtime : 1780650771
  fsdb_size  : 497468
  fsdb_dev   : 66307
  fsdb_inode : 3558781

summary:
  id        : xout_current_20260630_regen
  session_id: xout_current_20260630_regen
  healthy   : true
  status    : healthy
  message   : Session is healthy

health:
  id        : xout_current_20260630_regen
  session_id: xout_current_20260630_regen
  healthy   : true
  status    : healthy
  message   : Session is healthy
```

## scope.roots

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "scope.roots",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "source": "auto"
  }
}
```

xout rc=0:
```text
@xdebug.scope.roots.v1
summary:
  recommended: xring_tb_top
  source     : auto
  roots      : 1
  matched    : 1
  wave       : 1
  design     : 1

roots:
  path          status   sources      wave          design
  xring_tb_top  matched  design,wave  xring_tb_top  xring_tb_top
```

## scope.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "scope.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "path": "xring_tb_top.u_dut",
    "recursive": false
  },
  "limits": {
    "max_rows": 12
  }
}
```

xout rc=0:
```text
@xdebug.scope.list.v1
summary:
  path                 : xring_tb_top.u_dut
  recursive            : false
  returned_signal_count: 12
  total_signal_count   : 13178
  truncated            : true

data:
  path     : xring_tb_top.u_dut
  recursive: false
  scopes   : [empty]

signals:
  xring_tb_top.u_dut.irq
  xring_tb_top.u_dut.ds_vld
  xring_tb_top.u_dut.ds_qid
  xring_tb_top.u_dut.ds_valid_bytes
  xring_tb_top.u_dut.init_done
  xring_tb_top.u_dut.dfx_ring_mgr_state
  xring_tb_top.u_dut.dfx_pf_state
  xring_tb_top.u_dut.dfx_sched_state
  xring_tb_top.u_dut.clk
  xring_tb_top.u_dut.rst_n
  xring_tb_top.u_dut.paddr
  xring_tb_top.u_dut.psel
```

## value.at

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "value.at",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "time": "50000ns",
    "format": "hex"
  }
}
```

xout rc=0:
```text
@xdebug.value.at.v1
target:
  signal: xring_tb_top.u_dut.ds_vld
  time  : 50000ns

summary:
  status: ok
  value : 'h0
```

## value.batch_at

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signals": [
      "xring_tb_top.u_dut.ds_vld",
      "xring_tb_top.u_dut.ds_bp",
      "xring_tb_top.psel"
    ],
    "time": "50000ns",
    "format": "hex"
  }
}
```

xout rc=0:
```text
@xdebug.value.batch_at.v1
target:
  time        : 50000ns
  signal_count: 3

values:
  signal                     value  status
  xring_tb_top.u_dut.ds_vld  'h0    ok
  xring_tb_top.u_dut.ds_bp   'h0    ok
  xring_tb_top.psel          'h0    ok
```

## signal.statistics

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "signal.statistics",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_bp",
    "clock": "xring_tb_top.clk",
    "time_range": {
      "begin": "0ns",
      "end": "200000ns"
    },
    "max_samples": 200000
  }
}
```

xout rc=0:
```text
@xdebug.signal.statistics.v1
data:
  signal           : xring_tb_top.u_dut.ds_bp
  clock            : xring_tb_top.clk
  sampling         : posedge
  sampling_mode    : clock
  begin            : 0ns
  end              : 200000ns
  sample_count     : 200000
  known_count      : 200000
  unknown_count    : 0
  transition_count : 5941
  truncated        : false
  first            : 1'h1
  final            : 1'h0
  min              : 1'h0
  max              : 1'h1
  low_cycles       : 192554
  high_cycles      : 7446
  high_ratio       : 0.03723
  first_change_time: 20.5ns
  last_change_time : 10416.5ns

activity:
  high_burst_count: 2971
  first_high_time : 0.5ns
  last_high_time  : 10415.5ns
  last_fall_time  : 10416.5ns
  max_high_cycles : 20
```

## signal.changes

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "signal.changes",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_bp",
    "time_range": {
      "begin": "10400ns",
      "end": "10420ns"
    }
  },
  "limits": {
    "max_events": 16
  }
}
```

xout rc=0:
```text
@xdebug.signal.changes.v1
data:
  signal                 : xring_tb_top.u_dut.ds_bp
  begin                  : 10400ns
  end                    : 10420ns
  returned_change_rows   : 11
  includes_initial_value : true
  actual_transition_count: 10
  semantic_note          : signal.changes returns value-change rows for timeline inspection. Do not use row counts as sampled high cycles; use signal.statistics.high_cycles for clock-sampled activity.
  transition_count       : 10
  truncated              : false
  initial_value          : 1'h0
  final_value            : 1'h0
  first_change           : 10400ns
  last_change            : 10416.5ns
```

## signal.stability

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "signal.stability",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_bp",
    "time_range": {
      "begin": "10500ns",
      "end": "200000ns"
    }
  }
}
```

xout rc=0:
```text
@xdebug.signal.stability.v1
data:
  signal: xring_tb_top.u_dut.ds_bp
  begin : 10500ns
  end   : 200000ns

changes:
  time     value
  10500ns  1'h0
  transition_count: 1
  truncated       : false
  initial_value   : 1'h0
  final_value     : 1'h0
  first_change    : 10500ns
  last_change     : 10500ns
  stable          : true
  value           : 1'h0
```

## signal.resolve

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "signal.resolve",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld"
  }
}
```

xout rc=0:
```text
@xdebug.signal.resolve.v1
summary:
  count    : 1
  ok       : true
  query    : xring_tb_top.u_dut.ds_vld
  status   : ok
  truncated: false

data:
  count: 1

matches:
  file                              line  signal                     type
  <xring-repo>/rtl/xring_top.v  68    xring_tb_top.u_dut.ds_vld  net
  ok       : true
  query    : xring_tb_top.u_dut.ds_vld
  status   : ok
  truncated: false
```

## signal.canonicalize

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "signal.canonicalize",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld"
  }
}
```

xout rc=0:
```text
@xdebug.signal.canonicalize.v1
summary:
  query    : xring_tb_top.u_dut.ds_vld
  ambiguous: false

data:
  query          : xring_tb_top.u_dut.ds_vld
  canonical      : xring_tb_top.u_dut.ds_vld
  ambiguous      : false
  aliases        : [empty]
  fsdb_candidates: [empty]
  port_mappings  : [empty]
```

## event.config.load

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "event.config.load",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "ev0",
    "expr": "xring_tb_top.u_dut.ds_bp == 1'b0 && xring_tb_top.u_dut.ds_vld == 1'b1",
    "signals": {
      "ready": "xring_tb_top.u_dut.ds_bp",
      "valid": "xring_tb_top.u_dut.ds_vld"
    },
    "clock": "xring_tb_top.clk"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : event.config.load
code       : INVALID_REQUEST
message    : args.config or args.config_path required
recoverable: true
```

## event.config.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "event.config.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=0:
```text
@xdebug.event.config.list.v1
data:
  count : 0
  events: [empty]
```

## event.find

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "ev0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    },
    "max_examples": 8
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : event.find
code       : MISSING_FIELD
message    : args.expr is required
recoverable: true
```

## event.export

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "event.export",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "ev0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    },
    "format": "rows"
  },
  "limits": {
    "max_events": 8
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : event.export
code       : MISSING_FIELD
message    : args.expr is required
recoverable: true
```

## handshake.inspect

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "handshake.inspect",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "clock": "xring_tb_top.clk",
    "valid": "xring_tb_top.u_dut.ds_vld",
    "ready": "xring_tb_top.u_dut.ds_bp",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  },
  "limits": {
    "max_samples": 1000
  }
}
```

xout rc=0:
```text
@xdebug.handshake.inspect.v1
summary:
  sample_count    : 1001
  transfer_count  : 0
  max_stall_cycles: 16
  truncated       : true

data:
  sample_count              : 1001
  transfer_count            : 0
  max_stall_cycles          : 16
  ready_without_valid_cycles: 293
  data_stability_violations : 0
  truncated                 : true
  findings                  : [empty]
```

## detect_abnormal

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "detect_abnormal",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signals": [
      "xring_tb_top.u_dut.ds_vld",
      "xring_tb_top.u_dut.ds_bp"
    ],
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=0:
```text
@xdebug.detect_abnormal.v1
summary:
  finding_count: 0
  truncated    : false

data:
  finding_count: 0
  findings     : [empty]
  truncated    : false
```

## verify.conditions

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "verify.conditions",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "time": "50000ns",
    "conditions": [
      {
        "signal": "xring_tb_top.u_dut.ds_vld",
        "op": "==",
        "value": "'h0"
      },
      {
        "signal": "xring_tb_top.u_dut.ds_bp",
        "op": "==",
        "value": "'h0"
      }
    ]
  }
}
```

xout rc=0:
```text
@xdebug.verify.conditions.v1
summary:
  time           : 50000ns
  verdict        : pass
  condition_count: 2
  all_passed     : true
  passed         : 2
  failed         : 0
  unknown        : 0

checks:
  signal                     time     op  expected  observed  known  status  pass
  xring_tb_top.u_dut.ds_vld  50000ns  ==  'h0       'h0       true   pass    true
  xring_tb_top.u_dut.ds_bp   50000ns  ==  'h0       'h0       true   pass    true
```

## window.verify

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "window.verify",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    },
    "condition": "known"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : window.verify
code       : MISSING_FIELD
message    : args.clock is required
recoverable: true
```

## expr.eval_at

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "expr.eval_at",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "expr": "xring_tb_top.u_dut.ds_vld && !xring_tb_top.u_dut.ds_bp",
    "time": "10469.5ns"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : expr.eval_at
code       : MISSING_FIELD
message    : args.signals is required
recoverable: true
```

## counter.statistics

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "counter.statistics",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_bp",
    "clock": "xring_tb_top.clk",
    "time_range": {
      "begin": "0ns",
      "end": "200000ns"
    },
    "max_samples": 200000
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : counter.statistics
code       : MISSING_FIELD
message    : args.vld is required
recoverable: true
```

## sampled_pulse.inspect

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "sampled_pulse.inspect",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "clock": "xring_tb_top.clk",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : sampled_pulse.inspect
code       : MISSING_FIELD
message    : args.valid is required
recoverable: true
```

## trace.driver

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "trace.driver",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.rst_n"
  },
  "limits": {
    "max_results": 3
  },
  "output": {
    "verbosity": "full"
  }
}
```

xout rc=0:
```text
@xdebug.trace.driver.v1
summary:
  signal    : xring_tb_top.rst_n
  mode      : driver
  path_count: 2
  truncated : false

source: <xring-repo>/dv/tb/xring_tb_top.sv:21-23
   18 |     end
   19 | 
   20 |     initial begin
>  21 |         rst_n = 1'b0;
   22 |         repeat (20) @(posedge clk);
>  23 |         rst_n = 1'b1;
   24 |     end
   25 | 
   26 |     initial begin

active_signals:
  line  signal_path
  21    xring_tb_top.rst_n
  23    xring_tb_top.rst_n
```

## trace.load

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "trace.load",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.rst_n"
  },
  "limits": {
    "max_results": 3
  },
  "output": {
    "verbosity": "full"
  }
}
```

xout rc=0:
```text
@xdebug.trace.load.v1
summary:
  signal    : xring_tb_top.rst_n
  mode      : load
  path_count: 3
  truncated : true
  limit_hint: returned first 3 trace entries; increase limits.max_results to return all results

source: third_party/xif_agent/src/xif_if.sv:372
  369 |       dbg_success_streak = 0;
  370 |     end else begin
  371 |       if (mon_cb.vld === 1'b1) begin
> 372 |         pd_bits = mon_cb.pd;
  373 |         if ($isunknown(pd_bits)) begin
  374 |           uvm_report_error("XIF_PD_X", $sformatf("pd contains X/Z while vld is asserted at %0t", $time), UVM_NONE);
  375 |         end

active_signals:
  line  signal_path
  372   xring_tb_top.rst_n -> xring_tb_top.u_hvp.top_if.ds_monitor_if.unnamed$$_1.pd_bits
  372   xring_tb_top.rst_n -> xring_tb_top.u_hvp.top_if.credit_drv_if.unnamed$$_1.pd_bits
  372   xring_tb_top.rst_n -> xring_tb_top.u_hvp.top_if.grp_credit_drv_if.unnamed$$_1.pd_bits
```

## source.context

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "source.context",
  "args": {
    "file": "<xverif-repo>/xdebug/testdata/design/uart/uart_16550.sv",
    "line": 164,
    "context_lines": 3,
    "include_source": true
  }
}
```

xout rc=0:
```text
@xdebug.source.context.v1
summary:
  file: <xverif-repo>/xdebug/testdata/design/uart/uart_16550.sv
  line: 164

data:
  context_kind: if

enclosing:
  begin_line: 156
  end_line  : 167
  type      : if

context:
  line  text                                    hit
  161                                           false
  162                                           false
  163   // handle loopback                      false
  164   assign RXDin = loopback ? TXD : RXD;    true
  165   assign TXD = loopback ? 1'b1 : TXDout;  false
  166                                           false
  167   endmodule: uart_16550                   false
```

## expr.normalize

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "expr.normalize",
  "args": {
    "expr": "valid && !ready"
  }
}
```

xout rc=0:
```text
@xdebug.expr.normalize.v1
summary:
  expr      : valid && !ready
  source    : string_fallback
  confidence: low

args:
  name   type    op
  valid  signal
                 not
  op               : and
  confidence_reason: parsed from raw string without NPI handle
```

## trace.active_driver

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "requested_time": "50000ns"
  },
  "output": {
    "verbosity": "full"
  }
}
```

xout rc=0:
```text
@xdebug.trace.active_driver.v1
summary:
  signal        : xring_tb_top.u_dut.ds_vld
  requested_time: 50000ns
  active_time   : 12466.5ns
  path_count    : 7
  truncated     : false

source: <xring-repo>/rtl/scheduler.v:61
   58 |     input  wire                         comp_wr_err,
   59 | 
   60 |     // ---- Downstream VLD/BP interface ----
>  61 |     output reg                          ds_vld,
   62 |     input  wire                         ds_bp,
   63 |     output reg  [DATA_W-1:0]           ds_data,
   64 |     output reg  [QID_W-1:0]            ds_qid,

active_signals:
  line  signal_path
  61    xring_tb_top.u_dut.u_scheduler.ds_vld -> xring_tb_top.u_dut.ds_vld

source: <xring-repo>/rtl/scheduler.v:818-819
  815 |                     {{(DATA_W-1){1'b0}}, 1'b1};
  816 | end
  817 | 
> 818 | always @(*) begin
> 819 |     ds_vld         = (ob_state == OB_OUTPUT) && ob_valid && !ds_bp;
  820 |     ds_data        = shifted_data & byte_mask;
  821 |     ds_qid         = ob_qid;
  822 |     ds_grp_id      = ob_grp_id;

active_signals:
  line  signal_path
  819   xring_tb_top.u_dut.u_scheduler.ob_valid -> xring_tb_top.u_dut.u_scheduler.ob_state -> xring_tb_top.u_dut.u_scheduler.OB_OUTPUT -> xring_tb_top.u_dut.u_scheduler.ds_bp -> xring_tb_top.u_dut.ds_vld
  818   xring_tb_top.u_dut.ds_vld

source: <xring-repo>/rtl/xring_top.v:68
   65 |     output wire         bready,
   66 | 
   67 |     // ---- Downstream VLD/BP Interface ----
>  68 |     output wire         ds_vld,
   69 |     input  wire         ds_bp,
   70 |     output wire [511:0] ds_data,
   71 |     output wire [3:0]   ds_qid,

active_signals:
  line  signal_path
  68    xring_tb_top.u_dut.ds_vld -> xring_tb_top.ds_vld

source: <xring-repo>/rtl/scheduler.v:61
   58 |     input  wire                         comp_wr_err,
   59 | 
   60 |     // ---- Downstream VLD/BP interface ----
>  61 |     output reg                          ds_vld,
   62 |     input  wire                         ds_bp,
   63 |     output reg  [DATA_W-1:0]           ds_data,
   64 |     output reg  [QID_W-1:0]            ds_qid,

active_signals:
  line  signal_path
  61    xring_tb_top.u_dut.u_scheduler.ds_vld -> xring_tb_top.ds_vld

source: <xring-repo>/rtl/scheduler.v:818-819
  815 |                     {{(DATA_W-1){1'b0}}, 1'b1};
  816 | end
  817 | 
> 818 | always @(*) begin
> 819 |     ds_vld         = (ob_state == OB_OUTPUT) && ob_valid && !ds_bp;
  820 |     ds_data        = shifted_data & byte_mask;
  821 |     ds_qid         = ob_qid;
  822 |     ds_grp_id      = ob_grp_id;

active_signals:
  line  signal_path
  819   xring_tb_top.u_dut.u_scheduler.ob_valid -> xring_tb_top.u_dut.u_scheduler.ob_state -> xring_tb_top.u_dut.u_scheduler.OB_OUTPUT -> xring_tb_top.u_dut.u_scheduler.ds_bp -> xring_tb_top.ds_vld
  818   xring_tb_top.ds_vld
```

## trace.active_driver_chain

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver_chain",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signal": "xring_tb_top.u_dut.ds_vld",
    "requested_time": "50000ns",
    "clk_period": "1ns"
  },
  "limits": {
    "max_nodes": 4
  },
  "output": {
    "verbosity": "full"
  }
}
```

xout rc=0:
```text
@xdebug.trace.active_driver_chain.v1
summary:
  signal     : xring_tb_top.u_dut.ds_vld
  start_time : 50000ns
  hop_count  : 1
  termination: ambiguous
  truncated  : false

source: <xring-repo>/rtl/scheduler.v:819
  816 | end
  817 | 
  818 | always @(*) begin
> 819 |     ds_vld         = (ob_state == OB_OUTPUT) && ob_valid && !ds_bp;
  820 |     ds_data        = shifted_data & byte_mask;
  821 |     ds_qid         = ob_qid;
  822 |     ds_grp_id      = ob_grp_id;

active_signals:
  hop  line  signal_path
  0    819   xring_tb_top.u_dut.ds_vld
```

## cursor.set

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "cursor.set",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "c0",
    "time": "50000ns"
  }
}
```

xout rc=0:
```text
@xdebug.cursor.set.v1
cursor:
  name      : c0
  time      : 50000ns
  origin    : manual
  created_at: 1782799310
  updated_at: 1782799310

resolved_time:
  source: 50000ns
  time  : 50000ns
  status: set
```

## cursor.get

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "cursor.get",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "c0"
  }
}
```

xout rc=0:
```text
@xdebug.cursor.get.v1
cursor:
  name      : c0
  time      : 50000ns
  origin    : manual
  created_at: 1782799310
  updated_at: 1782799310
```

## cursor.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "cursor.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=0:
```text
@xdebug.cursor.list.v1
cursors:
  name  time     note  origin  clock  created_at  updated_at
  c0    50000ns        manual         1782799310  1782799310
  active_cursor: c0
  cursor_count : 1
```

## cursor.use

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "cursor.use",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "c0"
  }
}
```

xout rc=0:
```text
@xdebug.cursor.use.v1
data:
  status       : active
  active_cursor: c0

cursor:
  name      : c0
  time      : 50000ns
  origin    : manual
  created_at: 1782799310
  updated_at: 1782799310
```

## cursor.delete

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "cursor.delete",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "c0"
  }
}
```

xout rc=0:
```text
@xdebug.cursor.delete.v1
data:
  status: deleted
  name  : c0
```

## list.create

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.create",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0",
    "signals": [
      "xring_tb_top.u_dut.ds_vld",
      "xring_tb_top.u_dut.ds_bp"
    ]
  }
}
```

xout rc=0:
```text
@xdebug.list.create.v1
summary:
  name   : l0
  status : created
  created: true
```

## list.show

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.show",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0"
  }
}
```

xout rc=0:
```text
@xdebug.list.show.v1
summary:
  name        : l0
  signal_count: 2

signals:
  index  signal
  1      xring_tb_top.u_dut.ds_vld
  2      xring_tb_top.u_dut.ds_bp
```

## list.value_at

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.value_at",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0",
    "time": "50000ns"
  }
}
```

xout rc=0:
```text
@xdebug.list.value_at.v1
summary:
  name        : l0
  time        : 50000ns
  signal_count: 2

values:
  xring_tb_top.u_dut.ds_vld: 0
  xring_tb_top.u_dut.ds_bp : 0
```

## list.add

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.add",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0",
    "signals": [
      "xring_tb_top.psel"
    ]
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : list.add
code       : MISSING_FIELD
message    : args.signal is required
recoverable: true
```

## list.diff

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.diff",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0",
    "time_a": "10469.5ns",
    "time_b": "10470.5ns"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : list.diff
code       : MISSING_FIELD
message    : args.begin is required
recoverable: true
```

## list.validate

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.validate",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0"
  }
}
```

xout rc=0:
```text
@xdebug.list.validate.v1
summary:
  name     : l0
  all_found: true

signals:
  signal                     status
  xring_tb_top.u_dut.ds_vld  ok
  xring_tb_top.u_dut.ds_bp   ok
```

## list.export

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.export",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0",
    "time": "50000ns"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : list.export
code       : MISSING_FIELD
message    : list.export requires begin/end
recoverable: true
```

## list.delete

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "list.delete",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "l0"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : list.delete
code       : MISSING_FIELD
message    : args.signal or args.index
recoverable: true
```

## apb.config.load

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "apb.config.load",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "apb0",
    "clock": "xring_tb_top.clk",
    "psel": "xring_tb_top.u_dut.psel",
    "penable": "xring_tb_top.u_dut.penable",
    "pready": "xring_tb_top.u_dut.pready",
    "paddr": "xring_tb_top.u_dut.paddr",
    "pwrite": "xring_tb_top.u_dut.pwrite",
    "pwdata": "xring_tb_top.u_dut.pwdata",
    "prdata": "xring_tb_top.u_dut.prdata"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : apb.config.load
code       : INVALID_REQUEST
message    : args.config or args.config_path required
recoverable: true
```

## apb.config.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "apb.config.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : apb.config.list
code       : MISSING_FIELD
message    : args.name is required
recoverable: true
```

## apb.query

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "apb.query",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "apb0",
    "time_range": {
      "begin": "0ns",
      "end": "200000ns"
    }
  },
  "limits": {
    "max_transactions": 3
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : apb.query
code       : ANALYZE_FAILED
message    : APB config not found: apb0
recoverable: true
```

## apb.cursor

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "apb.cursor",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "apb0",
    "time": "50000ns"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : apb.cursor
code       : MISSING_FIELD
message    : args.op is required
recoverable: true
```

## apb.transfer_window

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "apb.transfer_window",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "apb0",
    "time_range": {
      "begin": "0ns",
      "end": "200000ns"
    }
  },
  "limits": {
    "max_transactions": 3
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : apb.transfer_window
code       : ACTION_FAILED
message    : APB config not found: apb0
recoverable: true
```

## axi.config.load

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.config.load",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "clock": "xring_tb_top.clk",
    "valid": "xring_tb_top.u_dut.ds_vld",
    "ready": "xring_tb_top.u_dut.ds_bp"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.config.load
code       : INVALID_REQUEST
message    : args.config or args.config_path required
recoverable: true
```

## axi.config.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.config.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.config.list
code       : MISSING_FIELD
message    : args.name is required
recoverable: true
```

## axi.query

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  },
  "limits": {
    "max_transactions": 3
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.query
code       : ANALYZE_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## axi.analysis

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.analysis",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.analysis
code       : ANALYZE_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## axi.channel_stall

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.channel_stall",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "channel": "r",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.channel_stall
code       : ACTION_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## axi.latency_outlier

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.latency_outlier",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.latency_outlier
code       : ACTION_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## axi.outstanding_timeline

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.outstanding_timeline",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.outstanding_timeline
code       : ACTION_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## axi.request_response_pair

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "axi.request_response_pair",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "axi0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : axi.request_response_pair
code       : ACTION_FAILED
message    : AXI config not found: axi0
recoverable: true
```

## stream.config.load

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "s0",
    "clock": "xring_tb_top.clk",
    "valid": "xring_tb_top.u_dut.ds_vld",
    "ready": "xring_tb_top.u_dut.ds_bp",
    "payload": "xring_tb_top.u_dut.ds_qid"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : stream.config.load
code       : MISSING_FIELD
message    : args.streams is required
recoverable: true
```

## stream.config.list

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.list",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {}
}
```

xout rc=0:
```text
@xdebug.stream.config.list.v1
summary:
  count: 0

data:
  streams: [empty]
```

## stream.query

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "s0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  },
  "limits": {
    "max_rows": 8
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : stream.query
code       : MISSING_FIELD
message    : args.stream is required
recoverable: true
```

## stream.show

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "stream.show",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "s0"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : stream.show
code       : MISSING_FIELD
message    : args.stream is required
recoverable: true
```

## stream.validate

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "stream.validate",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "name": "s0",
    "time_range": {
      "begin": "10000ns",
      "end": "13000ns"
    }
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : stream.validate
code       : MISSING_FIELD
message    : args.stream is required
recoverable: true
```

## rc.generate

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "rc.generate",
  "target": {
    "session_id": "xout_current_20260630_regen"
  },
  "args": {
    "signals": [
      "xring_tb_top.u_dut.ds_vld",
      "xring_tb_top.u_dut.ds_bp"
    ],
    "time": "50000ns"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : rc.generate
code       : MISSING_FIELD
message    : args.config_path is required
recoverable: true
```

## batch

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "batch",
  "args": {
    "mode": "continue_on_error",
    "requests": [
      {
        "api_version": "xdebug.v1",
        "action": "value.at",
        "target": {
          "session_id": "xout_current_20260630_regen"
        },
        "args": {
          "signal": "xring_tb_top.u_dut.ds_vld",
          "time": "50000ns"
        }
      },
      {
        "api_version": "xdebug.v1",
        "action": "signal.resolve",
        "target": {
          "session_id": "xout_current_20260630_regen"
        },
        "args": {
          "signal": "xring_tb_top.u_dut.ds_vld"
        }
      }
    ]
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : batch
code       : BATCH_PARTIAL_FAILURE
message    : one or more child requests failed
recoverable: true
```

## session.gc

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "session.gc",
  "args": {}
}
```

xout rc=0:
```text
@xdebug.session.gc.v1
summary:
  status       : completed
  before_count : 8
  kept_count   : 8
  removed_count: 0

before:
  id                                session_id                        mode      daidir                                                                          fsdb                                                                           socket_path                                                                  transport  file_dir                                                                        server_host            server_pid  created_at  last_active  dbdir_mtime  dbdir_size  dbdir_dev  dbdir_inode  fsdb_mtime  fsdb_size  fsdb_dev  fsdb_inode
  xout_current_20260630             xout_current_20260630             combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_f68723fc1c2acbb9/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_f68723fc1c2acbb9/transport  localhost.localdomain  2879498     1782790678  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_b           xout_current_20260630_b           combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_09750ab00d736010/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_09750ab00d736010/transport  localhost.localdomain  2881701     1782790854  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_c           xout_current_20260630_c           combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_09750bb00d7361c3/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_09750bb00d7361c3/transport  localhost.localdomain  2883339     1782790963  1782796130   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  active_driver_py_2918664          active_driver_py_2918664          combined  <xverif-repo>/xdebug/testdata/combined/active_driver/out/simv.daidir        <xverif-repo>/xdebug/testdata/combined/active_driver/out/waves.fsdb        ~/.xdebug/engine/sessions/active_driver_py_02e879d9c249d84d/socket  uds        ~/.xdebug/engine/sessions/active_driver_py_02e879d9c249d84d/transport  localhost.localdomain  2918683     1782796007  1782796130   1782715423   4096        66307      554070230    1782715423  9821       66307     1611510105
  if_port_root_py_2918664           if_port_root_py_2918664           combined  <xverif-repo>/xdebug/testdata/combined/interface_port_root/out/simv.daidir  <xverif-repo>/xdebug/testdata/combined/interface_port_root/out/waves.fsdb  ~/.xdebug/engine/sessions/if_port_root_py__1634e14c3170c8f0/socket  uds        ~/.xdebug/engine/sessions/if_port_root_py__1634e14c3170c8f0/transport  localhost.localdomain  2918741     1782796007  1782796130   1781511675   4096        66307      541233024    1781579586  9741       66307     1087379363
  xout_current_20260630_envtrace    xout_current_20260630_envtrace    combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_d4611ca55364fffe/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_d4611ca55364fffe/transport  localhost.localdomain  2921617     1782796126  1782799070   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_limitcheck  xout_current_20260630_limitcheck  combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_2d8694d322bf7e53/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_2d8694d322bf7e53/transport  localhost.localdomain  2940979     1782799143  1782799170   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781
  xout_current_20260630_regen       xout_current_20260630_regen       combined  <xring-repo>/dv/run/out/sanity/build/simv.daidir                            <xring-repo>/dv/run/out/sanity/test/tc_sanity_10q_100db/waves.fsdb         ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/socket  uds        ~/.xdebug/engine/sessions/xout_current_202_344baca0287e6f7b/transport  localhost.localdomain  2941852     1782799307  1782799311   1781509284   4096        66307      3553032      1780650771  497468     66307     3558781

kept:
  session_id                        mode
  xout_current_20260630             combined
  xout_current_20260630_b           combined
  xout_current_20260630_c           combined
  active_driver_py_2918664          combined
  if_port_root_py_2918664           combined
  xout_current_20260630_envtrace    combined
  xout_current_20260630_limitcheck  combined
  xout_current_20260630_regen       combined
  removed: [empty]
```

## session.close

request:
```json
{
  "api_version": "xdebug.v1",
  "action": "session.close",
  "args": {
    "id": "xout_current_20260630_regen"
  }
}
```

xout rc=1:
```text
@xdebug.error.v1

action     : session.close
code       : MISSING_FIELD
message    : args.session_id is required
recoverable: true
```
