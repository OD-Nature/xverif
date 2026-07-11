# xdebug 实战示例

本文给 AI agent 提供 xdebug 示例写法。示例采用“现象 -> 最小查询 -> 证据读取 -> 下一步”的结构，避免只堆命令。

## CLI 调用形态

CLI 场景下先用原生 `session.open` 打开 session，再把后续 action 放进完整 `xdebug.v1` request envelope。本文 JSON 片段都展示可交给 `tools/xdebug --json -` 的原生 request。

默认优先使用 xout 输出；只有脚本需要稳定读取 JSON 字段，或专门讲 JSON response/schema 时，才给 CLI 加 `--json`。

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "time": "100ns",
    "clock": "top.clk",
    "signals": [
      "top.u.valid",
      "top.u.ready"
    ],
    "format": "hex"
  },
  "limits": {}
}
```

MCP tool 参数壳请使用 `xverif-mcp`。

## Ready 卡低

现象：`valid` 保持为 1，但 `ready` 长时间为 0。

最小查询：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "time": "@stall",
    "clock": "top.clk",
    "signals": [
      "top.u_if.valid",
      "top.u_if.ready",
      "top.u_if.full",
      "top.u_if.state_q",
      "top.u_if.bp"
    ],
    "format": "hex"
  }
}
```

证据读取：

- `summary` 和 `data.values` 确认同一时间点的 valid/ready/full/state。
- 若 `ready=0` 且 `full=1`，下一步查 `full` 或 state 的 driver。
- 若返回 `truncated:true`，缩小 signal 列表或时间点，不要直接下结论。

下一步：

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "signal": "top.u_if.ready",
    "time": "@stall"
  }
}
```

最终回答保留 `ready` 的值、stall 时间、源码窗口中的有效行、`file:line` 和 `signal_path`。

## Valid 未被接受

现象：valid 有脉冲，但没有形成 transfer。

最小查询：

```json
{
  "api_version": "xdebug.v1",
  "action": "event.find",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "expr": "valid && !ready",
    "clock": "top.clk",
    "signals": {
      "valid": "top.u_if.valid",
      "ready": "top.u_if.ready"
    },
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "mode": "first"
  }
}
```

证据读取：

- 用 `summary.first` / `summary.last` 锁定事件时间。
- 如果 event 返回上下文信号为 `?` 或字段不完整，不要猜值；对事件时间补 `value.batch_at`。

下一步：

```json
{
  "api_version": "xdebug.v1",
  "action": "handshake.inspect",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "clock": "top.clk",
    "valid": "top.u_if.valid",
    "ready": "top.u_if.ready",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "rules": {
      "max_stall_cycles": 16
    }
  }
}
```

注意确认 ready 极性。active-high backpressure 不能直接当 active-high ready。

## 通用 Stream / 模块内部交互

现象：接口不是标准 AXI/APB，但有 `vld/rdy/data` 或 `vld/data` 语义；也可能是模块内部 request、pipeline stage、FIFO 出口或 RM/scoreboard 任务流。

优先复用项目配置：

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "config_path": "<project>/xdebug/configs/streams.json",
    "mode": "replace"
  }
}
```

如果项目还没有 `xdebug/configs/` 和 `xdebug/signals.md`，先询问用户是否创建，并建议把维护规则写入项目 `AGENTS.md`。同时询问用户是否使用 xwiki 维护稳定信号路径、stream 配置索引、接口语义和常见查询流程；用户确认前不要写入 xwiki。

### 模块内部 request stream

自定义 request 不是标准总线，但可抽象成 `req_vld && req_rdy` 接受一笔任务。

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "streams": [
      {
        "name": "core_req",
        "signals": {
          "clk": "top.clk",
          "req_vld": "top.u_core.req_vld",
          "req_rdy": "top.u_core.req_rdy",
          "opcode_sig": "top.u_core.req_opcode",
          "id_sig": "top.u_core.req_id",
          "addr_sig": "top.u_core.req_addr",
          "data_sig": "top.u_core.req_data"
        },
        "clock": "clk",
        "edge": "negedge",
        "vld": "req_vld",
        "rdy": "req_rdy",
        "data_fields": {
          "opcode": "opcode_sig",
          "id": "id_sig",
          "addr": "addr_sig",
          "data": "data_sig"
        }
      }
    ],
    "mode": "replace"
  }
}
```

查某类任务：

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "core_req",
    "query": "match_field",
    "match": {
      "field": "opcode",
      "op": "==",
      "value": "8'h5a"
    },
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "line_limit": 20
  }
}
```

### Pipeline stage stall

pipeline stage 内部 `stage2_vld/stage2_rdy` 长时间不能前进时，把该 stage 当 stream。

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "streams": [
      {
        "name": "stage2",
        "signals": {
          "clk": "top.clk",
          "vld": "top.u_pipe.stage2_vld",
          "rdy": "top.u_pipe.stage2_rdy",
          "tag_sig": "top.u_pipe.stage2_tag",
          "state_sig": "top.u_pipe.stage2_state",
          "payload_sig": "top.u_pipe.stage2_payload"
        },
        "clock": "clk",
        "edge": "negedge",
        "vld": "vld",
        "rdy": "rdy",
        "data_fields": {
          "tag": "tag_sig",
          "state": "state_sig",
          "payload": "payload_sig"
        }
      }
    ]
  }
}
```

查 stall 窗口：

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "stage2",
    "query": "stall_window",
    "time_range": {
      "begin": "20us",
      "end": "30us"
    },
    "line_limit": 10
  }
}
```

### FIFO / queue 出口 backpressure

FIFO 出口 `deq_vld/deq_rdy/deq_data` 可直接作为 stream，用于定位消费者不接收还是生产者无数据。

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "streams": [
      {
        "name": "fifo_deq",
        "signals": {
          "clk": "top.clk",
          "vld": "top.u_fifo.deq_vld",
          "rdy": "top.u_fifo.deq_rdy",
          "data_sig": "top.u_fifo.deq_data"
        },
        "clock": "clk",
        "edge": "negedge",
        "vld": "vld",
        "rdy": "rdy",
        "data": "data_sig"
      }
    ]
  }
}
```

先查第一处 stall，再对该时间补 `value.batch_at` 或 `trace.active_driver`：

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "fifo_deq",
    "query": "first_stall",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "line_limit": 1
  }
}
```

### Packetized internal stream

有 `sop/eop/channel_id` 的内部包流可用 stream 查询某个 channel 的 packet。

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "streams": [
      {
        "name": "pkt_stream",
        "signals": {
          "clk": "top.clk",
          "vld": "top.u_pkt.vld",
          "rdy": "top.u_pkt.rdy",
          "sop": "top.u_pkt.sop",
          "eop": "top.u_pkt.eop",
          "channel_sig": "top.u_pkt.channel",
          "typ_sig": "top.u_pkt.typ",
          "seq_sig": "top.u_pkt.seq",
          "data_sig": "top.u_pkt.data"
        },
        "clock": "clk",
        "edge": "negedge",
        "vld": "vld",
        "rdy": "rdy",
        "sop": "sop",
        "eop": "eop",
        "channel_id": "channel_sig",
        "data_fields": {
          "typ": "typ_sig",
          "seq": "seq_sig",
          "data": "data_sig"
        }
      }
    ]
  }
}
```

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "pkt_stream",
    "query": "packet_window",
    "channel": "3",
    "time_range": {
      "begin": "0ns",
      "end": "200us"
    },
    "line_limit": 5
  }
}
```

大量 beat 使用 `stream.export`，不要把全量 packet beats 放进首轮回答：

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.export",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "pkt_stream",
    "kind": "packet_beats",
    "time_range": {
      "begin": "0ns",
      "end": "200us"
    },
    "output": {
      "path": "<project>/xdebug/out/pkt_stream.tsv",
      "file_format": "tsv"
    }
  }
}
```

### 只有 vld-data 的任务流

没有 ready 时，`transfer = vld`。适合抽取 task issue、scoreboard enqueue、RM input 等任务序列。

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "streams": [
      {
        "name": "task_issue",
        "signals": {
          "clk": "top.clk",
          "vld": "top.u_sched.task_vld",
          "type_sig": "top.u_sched.task_type",
          "arg0_sig": "top.u_sched.task_arg0",
          "arg1_sig": "top.u_sched.task_arg1"
        },
        "clock": "clk",
        "edge": "negedge",
        "vld": "vld",
        "data_fields": {
          "task_type": "type_sig",
          "arg0": "arg0_sig",
          "arg1": "arg1_sig"
        }
      }
    ]
  }
}
```

```json
{
  "api_version": "xdebug.v1",
  "action": "stream.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "stream": "task_issue",
    "query": "first_transfer",
    "time_range": {
      "begin": "0ns",
      "end": "50us"
    },
    "line_limit": 10
  }
}
```

## AXI latency 或通道 stall

现象：AXI read/write 响应慢，或某个 channel valid/ready 长时间不能握手。

最小查询先加载映射：

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.config.load",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "name": "axi0",
    "config": {
      "clock": "top.aclk",
      "rst_n": "top.aresetn",
      "arvalid": "top.u_axi.arvalid",
      "arready": "top.u_axi.arready",
      "araddr": "top.u_axi.araddr",
      "arid": "top.u_axi.arid",
      "rvalid": "top.u_axi.rvalid",
      "rready": "top.u_axi.rready",
      "rdata": "top.u_axi.rdata",
      "rresp": "top.u_axi.rresp",
      "rlast": "top.u_axi.rlast"
    }
  }
}
```

然后查 stall：

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.channel_stall",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "name": "axi0",
    "channel": "r",
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "line_limit": 20
  }
}
```

证据读取：

- 先看 `summary.sample_count`、`data.max_stall_cycles`、`data.findings[]`。
- 需要证明异常 transaction/beat 时，优先用 `axi.query` 的 `query.index` / `query.line_limit` 缩小，或用 `axi.export` 做批量导出。

## APB slow/error access

现象：APB 访问等待过长、读写数据不符合预期或 error response。

流程：

1. `apb.config.load` 注册 `clk/rst_n/paddr/psel/penable/pwrite/pwdata/prdata`，按需提供 `pready`。
2. `apb.query` 查目标时间窗口或地址。
3. 对 finding 时间用 `value.batch_at` 取 `psel/penable/pready/paddr/pwrite/pwdata/prdata`。

不要跳过 config.load。`apb.config.list` 只能列已加载配置，不会自动搜索 DUT。

### APB/AXI query 参数位置

`apb.query` / `axi.query` 的第 N 个 transfer/transaction 使用 1-based `args.query.index`；返回前 N 条使用 `args.query.line_limit`。不要写旧 `args.num`，也不要把数量限制猜成顶层数量字段。

正确：

```json
{
  "api_version": "xdebug.v1",
  "action": "apb.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "name": "apb0",
    "direction": "read",
    "query": {
      "index": 1
    }
  }
}
```

```json
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "name": "axi0",
    "direction": "write",
    "query": {
      "index": 1
    }
  }
}
```

常见错误反例，不要复制为请求：

```text
{
  "api_version": "xdebug.v1",
  "action": "axi.query",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "name": "axi0",
    "direction": "write",
    "num": 1
  }
}
```

上面的旧 `num` 会被 schema 拒绝；改用 `query.index`。

### active driver 链深度

`trace.active_driver_chain` 的递归深度放在 top-level `limits.max_depth`，不要写 `args.depth`。

```json
{
  "api_version": "xdebug.v1",
  "action": "trace.active_driver_chain",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "signal": "tb_top.u_dut.q",
    "time": "50ns"
  },
  "limits": {
    "max_depth": 8
  }
}
```

## X/Z 传播

现象：某信号出现 X/Z 或 `known:false`。

最小查询：

```json
{
  "api_version": "xdebug.v1",
  "action": "detect_abnormal",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "signals": [
      "top.u_if.data_leaf0",
      "top.u_if.data_leaf1",
      "top.u_if.valid",
      "top.u_if.ready"
    ],
    "time_range": {
      "begin": "0ns",
      "end": "100us"
    },
    "checks": [
      {
        "type": "unknown_xz"
      }
    ],
    "line_limit": 20
  }
}
```

证据读取：

- `known:false` 只是未知值证据，不是 root cause。
- packed struct / aggregate payload 必须由 AI 直接传最终 leaf signal path 检查；不要直接把 aggregate path 的 unknown finding 当作最终协议结论，也不要期待 xdebug 自动展开 struct。
- 找到第一处 unknown 后，用 `signal.changes` 缩小出现时间。
- combined session 下对同一时间调用 `trace.active_driver`。

## 地址或数据错误回溯

现象：总线地址、数据或 payload 与预期不一致。

思路：

1. 用 `value.batch_at` 同时取最终总线信号和候选上游路径，先确认错误来自哪条路径。
2. 对异常路径用 `trace.driver` 找赋值来源。
3. 用 `source.context` 读取赋值上下文。
4. 回到波形，用 `value.batch_at` 验证 driver 条件信号在异常时间的取值。

示例 batch：

```json
{
  "api_version": "xdebug.v1",
  "action": "value.batch_at",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "time": "10462510ps",
    "clock": "top.clk",
    "signals": [
      "top.u_arb.arb_addr",
      "top.u_arb.arb_src",
      "top.u_blk.req_addr",
      "top.u_entry.req_addr",
      "top.u_axi.araddr"
    ],
    "format": "hex",
    "slice_hint": {
      "chunk_width": 32,
      "count": 4
    }
  }
}
```

若响应包含 `xbit_hints.commands[]`，把字段切分交给 xbit，不要由 AI 心算大位宽 hex。

## event 性能或截断

现象：event 查询窗口很大、超时或返回截断。

处理：

- 先缩小 `time_range`，优先查 `event.find` 的 first/last，不要直接 `event.export` 全量 rows。
- 单信号变化用 bounded `signal.changes`；周期统计用 `signal.statistics` 加 clock。
- `truncated:true` 时继续缩小窗口或调整具体 limits，不要把返回样本当全集。

## 生成 nWave 证据视图

现象：需要给用户或同事一个能打开同一组信号和 marker 的 `signal.rc`。

流程：

1. 用前面的查询确定关键时间、关键 bus、handshake 信号和 root-cause 信号。
2. 写 JSON 配置，包含 groups、subgroups、markers、expr_signals。
3. 用 `rc.generate` 校验 FSDB 信号并生成 rc。

```json
{
  "api_version": "xdebug.v1",
  "action": "rc.generate",
  "target": {
    "session_id": "case_a"
  },
  "args": {
    "config_path": "wave_view.json",
    "output": {
      "path": "signal.rc"
    }
  }
}
```

默认不要把完整 rc 文本粘给用户；报告 `summary.rc_path`、marker、signal/group 计数和 validation 结果。

## 排障示例

现象：`SESSION_UNHEALTHY`、stdio-loop invalid JSON、socket timeout、license/NPI 失败。

定位顺序：

1. `xdebug log doctor --session <id> --json`
2. public actions：`actions.ndjson`
3. stdio-loop：`stdio.ndjson`
4. engine lifecycle：`lifecycle.ndjson`
5. transport：`transport.ndjson`
6. crash：`crash_marker.ndjson` 和 `log_health.ndjson`

对外共享日志前使用 `xdebug log bundle --session <id> --out debug_bundle.redacted.tgz --redact`。
