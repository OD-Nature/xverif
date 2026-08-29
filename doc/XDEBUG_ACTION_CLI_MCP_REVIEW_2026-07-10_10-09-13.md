# xdebug 全 action CLI/MCP 实测评审

- 评审时间：2026-07-10 10:09:13 +0800
- 评审范围：当前运行时与 `xdebug/schemas/v1/actions/*.request.schema.json` 共同公开的 70 个 action
- 调用入口：原生 CLI 与 MCP tool/stdio 两条真实路径
- 执行位置：所有 NPI/FSDB/daidir 与 MCP stdio-loop 调用均在沙箱外执行
- 每条路径的场景：正确参数、schema 层错误、schema 合法但 handler 层失败
- 核心判断：返回内容对实际 debug 是否有用；同时检查失败信息清晰度、可恢复性和内容冗余
- 证据原则：以本轮真实请求/响应为准；fixture、执行位置和无法覆盖项逐项披露；不以 basic example 或历史文档替代实测
- 执行约束：不调用、不导入、不复用仓库的 70-action replay runner、registry 或其输出；所有请求均在本轮按 action 独立构造并直接发送到 CLI/MCP 入口
- 原始证据：本轮 request/response JSONL 与 raw response 保存在 `<repo>/tmp/xverif-action-review-2026-07-10/`；本报告保留可版本化结论，临时原始证据不纳入仓库

## 评审口径

每个 action 均记录：

1. CLI 与 MCP 的三类调用是否真正到达预期层级。
2. 正确返回能否直接支持 debug 决策，是否缺少必要的信号、时间、值、来源或下一步提示。
3. schema 错误能否明确指出错误字段、期望类型/枚举和可复制修复方式。
4. handler 错误能否区分资源、语义、状态和环境问题，并给出可操作恢复建议。
5. CLI/MCP 语义是否一致，输出是否有无意义重复、过长 schema/元数据或上下文噪声。
6. 主 agent 结论后的“独立复核”由最终 review agent 逐项插入，不集中放在文末。

## 覆盖清单

- A 组：基础、session、design、combined，共 18 个。
- B 组：APB、AXI、stream，共 21 个。
- C 组：通用 waveform、cursor、list、event、value/verify，共 31 个。
- 合计：70 个。

## 覆盖结果与总评

- 70/70 action 均完成 CLI 正确场景；可通过 MCP 执行的 action 也均完成 MCP 正确场景。`session.doctor`、`session.gc`、`session.kill` 没有专用 MCP tool，generic query 被 `NATIVE_SESSION_ACTION_FORBIDDEN` 在 wrapper 层拦截，这是公开 action 与 MCP 暴露面的缺口。
- schema 负例均确认在 schema 或 MCP tool schema 层被拒绝。能构造 action handler 负例的 action 均用 schema 合法请求实证 `error_layer=handler`；`actions`、`session.list/gc`、`cursor.list`、`scope.list` 等天然返回合法集合/状态的入口没有伪造 handler 失败。
- CLI 与 MCP 对进入同一 backend action 的核心成功 payload 和错误 code/layer 总体一致；主要差异是 MCP 会把 `correct_example` 改写为 tool 参数壳，session 专用 tool 则走 managed session 生命周期。
- 对 debug 最有价值的一组包括 `trace.active_driver_chain`、`event.find`、`stream.query/validate`、`handshake.inspect`、`apb.query/transfer_window`、`axi.channel_stall`、`list.value_at`、`signal.statistics`、`verify.conditions/window.verify`：它们能返回时间、信号/事务、值、采样语义或根因链。
- 最高优先级的正确性/可解释性问题：`signal.changes` 声称返回 change rows 却没有实际 timeline rows；`value.at` 与 `value.batch_at` 在同 fixture/同时间给出的 clock bracket 不一致；`sampled_pulse.inspect` 在 `truncated=true` 后仍用陈旧的 45ns edge 解释 96ns 以后风险；`signal.canonicalize/resolve`、`trace.driver/load` 对 not-found 使用顶层 `ok=true`，容易造成假阳性理解。
- 其它高影响合同问题：APB/AXI 单笔事务 time 是无单位整数；APB/AXI config load/list 不回显主要信号/channel 映射；`stream.export` 的 `line_limit=5` 实际仍写 15059 rows；`verify.conditions` 的 transport `ok=true` 与语义 `verdict=fail` 需要更醒目的双层状态。
- 主要冗余来源：AXI outlier/query/pair 默认内嵌超宽 beat data；`stream.query/export` 在 summary 嵌入首末 transfer/stall；`event.export` 的 events 与 preview 完全重复；value/list value/verify 同时返回 values、sample_rows、samples 多套等价结构；失败响应经常在 summary/data/error 三层重复完整示例。
- 独立逐项复核结果：68 条“结论正确”、1 条“部分正确”、1 条“需修正”；纠偏意见已原位插在对应 action 后，没有集中放在文末。

## 逐 action 评审

<!-- ACTION_REVIEWS_APPEND_BELOW -->

### `apb.config.load`

- 实测请求：正确场景使用真实 APB VIP FSDB session，inline config 包含 clock/reset、PADDR/PSEL/PENABLE/PWRITE/PWDATA/PRDATA/PREADY/PSLVERR；schema 负例缺失 `args.name` 并加入未知字段；handler 负例给出不存在的 `args.config_path`。
- CLI：正确返回 `ok=true`、`status=loaded`；schema 负例为 `INVALID_REQUEST` / `error_layer=schema`；handler 负例为 `INVALID_ARGUMENT` / `error_layer=handler`。
- MCP stdio：三种结果与 CLI 的 code、layer 和核心 payload 一致；`correct_example` 已转换成 `xverif_debug_query` 的 MCP 参数壳，没有误导用户把 native envelope 塞进 MCP `args`。
- 正确返回的 debug 价值：中等。它能确认配置名、采样模式、clock、edge、sample point、reset、PREADY 和 PSLVERR，足以确认配置确实加载及部分关键采样语义；但返回的 `data.config` 没有回显 PADDR、PSEL、PENABLE、PWRITE、PWDATA、PRDATA 等已经提交的主要映射，无法仅凭本 action 的成功结果核实完整 APB 绑定。建议成功返回完整 effective config，或明确提示立即调用 `apb.config.list(name=...)` 做全量核验。
- 失败信息：schema 错误能准确指出缺失的 `args.name`、期望类型、schema 路径和可复制示例，恢复性好；但请求同时含未知字段时只报告第一个缺失字段，未提示未知字段。handler 错误清楚说明配置文件不存在并给出 inline/path 两条修复路径，不过 `invalid_arg` 写成 `args.config`，而实际出错字段是 `args.config_path`，字段定位不准确，应修正。
- 冗余度：偏高。JSON 的 `summary`、`data`、`error` 三处重复 `invalid_arg/expected/correct_example`；MCP 仅对示例壳做必要改写，其余重复与 CLI 相同。对 agent 而言保留 `error` 完整结构、`summary` 只留 code/message 即可。
- 主评审结论：功能可用，CLI/MCP 一致；最高优先级不是格式，而是成功结果缺少完整有效配置回显，其次是 handler 错误字段路径不准确。

> 独立复核：结论正确。CLI/MCP 成功响应均只回显采样语义及 PREADY/PSLVERR，handler 原始错误也确实把缺失的 `config_path` 定位为 `args.config`；完整映射缺失和失败三层重复均有 raw 支持。

### `stream.config.list`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功按 name 完整回显 alias→真实信号、vld/rdy/reset 表达式、data fields、channel 和 interleaving，debug 价值很高，明显优于 APB/AXI config.list。missing config 的字段定位和修复方向清楚。与 stream.show 内容接近，但 list(name) 作为配置发现入口仍合理；可让 args={} 只列名字以控制体积。

> 独立复核：结论正确。最终 retry 的 CLI/MCP 都完整返回 stream 定义，missing config 均为 `CONFIG_NOT_FOUND` / handler；该返回可直接核验信号绑定，debug 价值判断成立。

### `axi.request_response_pair`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功返回 20 笔配对事务的 request/data/response 时间与 latency，对慢响应、丢响应、配对错误 debug 很有用；但每笔都内嵌全部超宽 beat data/wstrb，严重冗余。默认应突出 missing response、latency、ID/address 和阶段时间，payload 按需展开。

> 独立复核：结论正确。两入口成功结果均含 20 笔 request/response 配对、阶段时间和 latency，同时逐 beat 携带宽 data/wstrb；高 debug 价值与高 payload 冗余判断均有依据。

### `axi.query`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功定位首笔 write 的 time/address/id/len/size/burst，debug 价值高；但 time=415000 无单位，且单个 transaction 默认带一条超宽全宽 data，宽总线下非常耗 token。建议 compact 返回 data hash/低位预览/beat count，完整 payload 由 verbose 控制。

> 独立复核：结论正确。CLI/MCP 命中相同首笔 write 并返回地址、ID、len/size/burst；事务时间为无单位数值且内嵌宽数据，所述可用性与 token 成本问题真实存在。

### `axi.outstanding_timeline`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功返回 160 个逐周期样本，能观察 outstanding 从 0 累积到 read=13/write=5，debug 价值高；但 summary 没有 peak_read/peak_write、peak_time、first_nonzero 等，agent 必须遍历长列表自己归纳。默认可返回峰值摘要+变化点压缩，raw per-cycle 放 verbose/export。

> 独立复核：结论正确。最终 debug retry 的两入口均返回 160 个逐周期样本，raw 可归纳出 read 峰值 13、write 峰值 5，但响应自身没有峰值及首个非零摘要；建议压缩变化点合理。

### `axi.latency_outlier`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功返回 5 个慢事务的 addr/id/beats/各阶段时间/latency，根因锚点很有用；但默认内嵌每个 beat 的超宽 data 和 wstrb，体积巨大，严重遮蔽 latency 证据。默认应只给元数据和首末/摘要，payload 用 verbose 或后续 query 获取。summary 为空也应给 outlier_count/max latency。

> 独立复核：结论正确。成功响应确有 5 个 outlier 及阶段时间/latency，并为每笔事务展开宽 beat payload；summary 缺少 outlier_count/max latency 的突出摘要，debug 锚点被大对象稀释。

### `axi.export`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功写出 3200 write+3200 read、6400 rows，返回 write/read/meta paths、requested range 与实际 scan range，debug 价值高且没有把大事务体塞回响应。应说明覆盖/覆盖写策略和 scan_end 小于 requested end 的原因。整体信息密度好。

> 独立复核：结论正确。最终 CLI/MCP 均报告 3200 write、3200 read、6400 rows 及 write/read/meta 路径，data 同时给 requested 与 scan range；未回灌事务明细，信息密度确实较好。

### `axi.cursor`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功给首笔 write 的地址、ID、len、方向，适合作为交互锚点，debug 价值高；但 time=415000 无单位，且没有 cursor index/总事务数，问题与 APB cursor 相同。missing config 恢复信息好，默认响应简洁。

> 独立复核：结论正确。retry 成功返回首笔 write 的地址、ID、len 和方向，时间仍是无单位数值，且没有 index/总数；handler retry 正确进入 `CONFIG_NOT_FOUND`，两入口核心语义一致。

### `axi.config.load`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功确认 loaded 和采样语义，却不回显任何 AXI channel mapping，加载成功无法证明绑定正确，debug 价值低到中。不存在 config_path 时错误却标 invalid_arg=args.config，应为 args.config_path。失败示例/字段重复偏高。

> 独立复核：结论正确。成功 data.config 只有 name、clock、edge、sample_point、reset，没有任一 AXI channel mapping；missing path 的 `invalid_arg=args.config` 也与实际字段不符。

### `axi.config.list`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功只回显 name、clock/edge/sample_point/reset，完全缺 AW/W/B/AR/R channel mapping，无法验证 AXI 配置是否绑对，debug 价值低。与能完整回显的 stream.config.list 差距明显。missing config handler 可恢复，summary 为空需补 name。

> 独立复核：结论正确。最终成功只返回 name 和采样/reset 信息，未返回 AW/W/B/AR/R 映射且 summary 为空；作为配置核验入口，debug 证据明显不足。

### `axi.channel_stall`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功在修正窗口扫描 2000 点，返回 29 transfers、max stall=30 cycles，并精确给出 15175..15475ns/30 cycles 与 23655..23875ns/22 cycles 两段 long stall，debug 价值很高。首轮大窗口会在交易前被限制截断，说明响应应突出 scanned_range/first_activity，帮助调用者缩窗。数据量合理。

> 独立复核：结论正确。最终 debug retry 明确返回 sample_count=2000、transfer_count=29、max_stall_cycles=30 及两段 30/22-cycle long stall；原始大窗口与修正窗口的差异也支持加强扫描范围提示。

### `axi.analysis`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功汇总 6360 个 latency samples 的 min/avg/max，但三个数值均无单位，且没有 p50/p95/p99、最慢事务 ID/时间，用户无法可靠解释量级。debug 价值中等，只能发现总体异常。missing config 恢复信息好；响应不冗余，主要是信息不足。

> 独立复核：结论正确。retry 响应仅给 6360 samples 的 min/avg/max，数值无单位、data 为空且没有分位数或最慢事务锚点；信息不冗余但不足以直接定位根因。

### `apb.config.list`

- 实测覆盖：CLI/MCP stdio 的最终 correct 均 ok=true；schema 负例均为 INVALID_REQUEST/schema；handler 负例均先独立通过 schema 再进入 handler，首轮失效证据不作为正确场景。
- 主评审：成功按 name 返回 clock/edge/sample_point/reset、PREADY/PSLVERR，能确认配置存在和采样语义；但完全不回显 PADDR/PSEL/PENABLE/PWRITE/PWDATA/PRDATA，无法审查接口最关键映射，debug 价值仅中等。missing name 的 handler 恢复信息较好。summary 为空也应补 name。

> 独立复核：结论正确。最终 CLI/MCP 仅回显 clock/edge/sample_point/reset/PREADY/PSLVERR，缺少六个主要 APB 信号映射且 summary 为空；missing name 的 handler 有明确恢复建议。

### `trace.active_driver_chain`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确返回 3 hops、termination=primary_input 和源码链，能给出完整根因路径，debug 价值很高。missing signal 的 `SIGNAL_NOT_FOUND` 带 message/invalid_arg/expected，明显优于单跳 action。约 5.5KB 与链路证据匹配，冗余可接受。

> 独立复核：结论正确。成功 raw 返回 hop_count=3、termination=primary_input 和逐 hop 源码证据；missing signal 为结构化 `SIGNAL_NOT_FOUND`，包含字段与期望，链式根因价值很高。

### `trace.active_driver`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确返回请求 time=20ns、实际 active_time=15ns 和 4 条活动路径/源码，直接支持时序根因定位，价值很高。missing signal 虽为 `SIGNAL_NOT_FOUND` / handler，但 message 仅泛化为 action failed、没有 invalid_arg/expected，恢复性显著弱于 chain 版本。6.6KB 证据基本合理。

> 独立复核：结论正确。成功 raw 同时给请求 20ns、实际 active_time=15ns 和 4 条路径；missing signal 的 handler 信息确实缺少 `invalid_arg/expected`，恢复性弱于 chain。

### `scope.roots`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：成功发现唯一 waveform root 并给 recommended_root/reason，debug 价值高。请求 design source 而 session 仅有 waveform 时仍 ok=true/root_count=0，但 limitations 会说明 design not loaded；信息可用但必须读深层字段。建议 summary 增加 complete/resource_available，避免把无资源误当无 root。

> 独立复核：结论正确。waveform 正例返回唯一 root 与推荐理由；`source=design` 在未加载 design 时仍 `ok=true/root_count=0`，只有 limitations 揭示资源缺失，存在误读风险。

### `trace.load`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确返回 5 条 load path 和源码证据，对影响面分析很有用；不存在信号同样 ok=true/path_count=0，存在严重歧义。JSON 约 7.8KB 主要是五段源码，可提供 compact paths 默认、源码按 verbose 展开。首要问题仍是 signal existence 语义。

> 独立复核：结论正确。成功返回 5 条 load path 及源码证据；不存在信号的 schema 合法请求仍 `ok=true/path_count=0`，未区分信号不存在和无 load，首要语义风险判断准确。

### `trace.driver`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确返回 3 条 driver path 和源码证据，debug 价值很高；不存在信号却 ok=true/path_count=0，无法区分“信号不存在”和“存在但无 driver”，会直接污染根因判断。应先返回 signal_found，空 driver 单独标 no_driver。多路径源码有合理体积。

> 独立复核：结论正确。成功返回 3 条 driver path；不存在信号同样 `ok=true/path_count=0`，raw 没有 `signal_found` 或 no-driver 状态，确会污染根因判断。

### `source.context`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确返回真实 file/line、enclosing 和源码窗口，对把 trace 证据落到 RTL 很有用；missing file 为 `SOURCE_NOT_FOUND`，包含 invalid_arg/expected。CLI 某次 summary 较空而 MCP 更完整，仍可恢复。默认源码窗口与目标匹配，无明显冗余。

> 独立复核：需修正。成功响应支持 file/line、context_kind 和 enclosing 范围，但没有返回实际源码窗口文本，不能称为“返回源码窗口”；因此它能定位 RTL 上下文，却仍需另一步读取源码。CLI handler 的 summary 为空、MCP summary 较完整及 `SOURCE_NOT_FOUND` 字段判断成立。

### `signal.resolve`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：存在信号给唯一 match；不存在信号顶层 ok=true，但 summary 内又有 ok=false/status=not_found/count=0。数据足以判断，却有双层 ok 冲突，调用方若只看 envelope 会误判。建议顶层 ok 仅表示 transport 时增加 `semantic_ok`，或 not_found 直接结构化失败。debug 能力高，合同表达需修。

> 独立复核：结论正确。存在信号返回唯一 match；不存在信号时 envelope `ok=true` 而 summary/data 为 `ok=false,status=not_found,count=0`，双层成功语义冲突由 raw 直接证实。

### `signal.canonicalize`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：存在信号能返回 canonical/alias/port mapping，debug 价值高；但不存在信号仍顶层 ok=true、ambiguous=false 并原样 canonical，极易把拼错路径当已确认路径。必须返回 found/status，not_found 应语义失败或至少 summary.found=false。体积合理，问题是正确性而非冗余。

> 独立复核：结论正确。不存在路径仍 `ok=true`、`ambiguous=false`，并把输入原样放进 canonical，且 rtl_path/leaf/scope 均为空；缺少 found/status 会把拼写错误伪装成确认结果。

### `expr.normalize`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：正确表达式只做 `string_fallback` 且 confidence=low；明显残缺的 `(` 也顶层 ok=true、原样返回，无法构造 handler 错误。它只能作为弱规范化提示，不能证明表达式可解析，对 debug 的实际价值偏低。建议返回 parsed=false/issues，或对语法错误给语义失败；响应本身简洁。

> 独立复核：结论正确。正常表达式和残缺的 `(` 都走 `string_fallback/confidence=low` 且顶层成功，证明该 action 只能提供弱文本归一化，不能作为解析有效性的证据。

### `session.close`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI native close 返回 removed=true；MCP 专用 close 也能清理 managed session。MCP 的 missing session 失败发生在 session manager，不是 native handler，层级未标注；应返回 `error_layer=wrapper/session_manager`。debug 信息足够且不冗余，但两入口关闭的资源所有权需要在响应中显式说明。

> 独立复核：结论正确。CLI native close 明确 `removed=true`，MCP 专用 close 能清理 managed alias；MCP missing-session 错误没有 `error_layer`，两入口资源所有权也未在统一响应中说明。

### `session.kill`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 成功明确 session/mode/removed=true，不存在 session 为 `SESSION_NOT_FOUND`；强制清理结果清楚。MCP 无专用 kill tool，generic query 三类场景均被 wrapper 禁止，形成明确覆盖缺口。建议 MCP 提供与 open/list/close 对称的 kill/doctor，或从公开 action catalog 标明 MCP unavailable。

> 独立复核：结论正确。CLI 成功和 `SESSION_NOT_FOUND` handler 均有实证；MCP 三次 generic query 都被 `NATIVE_SESSION_ACTION_FORBIDDEN` / wrapper 拒绝，未到 native handler，确属能力覆盖缺口。

### `session.gc`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 成功返回 before/kept/removed 计数，维护信息清楚；无残留时没有可构造 handler 失败。MCP 也被 `NATIVE_SESSION_ACTION_FORBIDDEN` 前置拒绝且无专用 tool，不能执行。debug 价值主要是环境维护而非定位 DUT；响应简洁。

> 独立复核：结论正确。CLI 返回 before/kept/removed 计数，空状态下再次调用仍成功而无法构造 handler 失败；MCP 三场景均在 wrapper 前置拒绝，价值主要是会话维护。

### `session.doctor`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 成功给 healthy、mode、resource、transport/log 诊断，debug 价值很高；不存在 session 为 `SESSION_NOT_FOUND` / handler。MCP generic query 的正确/schema/handler 三次都在 wrapper 被 `NATIVE_SESSION_ACTION_FORBIDDEN` 阻止，且没有对应专用 MCP doctor tool，因此本 action 当前无法通过 MCP 实际执行。这是 MCP 能力缺口，不应记作 action handler 失败。

> 独立复核：结论正确。CLI 正例包含 healthy/mode 及 health 诊断，不存在 session 为 handler 层 `SESSION_NOT_FOUND`；MCP 三次均为 wrapper 禁止，不能冒充 action handler 结果。

### `session.list`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 列 native 活动 session 与清理计数，MCP 列 managed alias/mode/backend，二者都对排查存活状态有用但不是同一集合。空列表是合法结果，handler 失败不可构造。MCP 默认带 pid 和绝对资源路径，内部诊断有用，普通 debug 偏噪且可能不宜外显；建议 compact 默认、doctor 取详细信息。

> 独立复核：结论正确。CLI 与 MCP 分别展示 native session 和 managed alias，空列表均为合法成功；MCP raw 确实带 pid/backend/绝对 resource，信息有诊断价值但默认偏噪。

### `session.open`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 正确返回 combined session id/mode，MCP 正确建立 managed alias/session；不存在资源的合法形状请求到 handler 失败。它对确认 transport/resources 很有用，但 CLI 与 MCP 生命周期合同不同，MCP 成功 summary 为空，关键 alias/mode/backend 藏在 data。应统一摘要并明确这是 native 还是 managed session。

> 独立复核：结论正确。CLI 返回 native session id/mode，MCP 建立 managed alias 且成功 summary 为空；两入口对不存在资源均进入 handler，但生命周期对象不同，建议显式区分合理。

### `schema`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 与 MCP 专用 schema tool 都返回 trace.driver 的精确 request schema/path；未知 action 为 `UNKNOWN_ACTION` / handler，MCP 参数形状错误先由 MCP schema 拒绝。对修复请求极有用，信息密度合适。建议 UNKNOWN_ACTION 同时返回相近 action 名。

> 独立复核：结论正确。CLI/MCP 正例都返回 trace.driver request schema/path，未知 action 为 handler 层 `UNKNOWN_ACTION`，MCP 外壳形状错误则先由 `mcp_schema` 拒绝；能力发现价值高。

### `batch`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 与 MCP query 内的 batch 成功返回 child results、count/all_ok；子请求未知 action 时顶层 `BATCH_PARTIAL_FAILURE`、all_ok=false，debug 价值高，因为能保留逐 child 证据。缺陷是顶层 batch error 没有 `error_layer`，需深入 child 才知真正层级；建议汇总 failed indexes/codes。体积与信息匹配。

> 独立复核：结论正确。两入口正例均保留 child result 与 count/all_ok；未知 child 使顶层 `BATCH_PARTIAL_FAILURE` 且 `error_layer` 为空，需下钻 child 才能定位层级，建议汇总失败索引有依据。

### `actions`

- 实测覆盖：按该 action 的 native CLI 与真实 MCP 暴露方式分别测试正确、schema 错误和 handler/语义失败；无法进入 native handler 的 MCP wrapper 限制逐项说明。
- 主评审：CLI 与 MCP 专用 list tool 均发现 70 implemented/1 removed，并给 category/status/requires/schema/examples/handler 元数据，能力发现价值高。成功 JSON 约 51KB，`implemented` 与 `actions[].name` 重复；应提供 compact catalog 或 include_descriptors 开关。action 无语义参数，handler 失败不可构造；MCP 非 object 参数由 MCP schema 拒绝。

> 独立复核：结论正确。两入口均返回 70 implemented、1 removed 及完整 descriptor，`implemented` 与 action 名列表存在重复且响应很大；无语义参数也确实无法构造 native handler 失败，MCP 非 object 由外层 schema 拒绝。

### `window.verify`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功明确 4 个 posedge-after samples 全部满足 always 条件，debug 价值高；但响应不回显请求窗口 140..175ns，证据缺少最关键的 proof 范围，必须补 begin/end。handler 字段定位清楚但 correct_example 回显坏 clock。返回不冗余。

> 独立复核：结论正确。成功 summary 只给 4 个样本全通过及采样语义，data 仅有 condition 统计，未回显 140..175ns 证明窗口；missing clock 的 correct_example 也原样保留坏路径。

### `verify.conditions`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：顶层 ok=true 只表示 action 执行成功，而 summary.verdict=fail/all_passed=false 正确表达 1 pass/1 fail；这对 debug 很重要，但调用方很容易只看 ok。建议增加 `semantic_ok=false` 或在 XOUT 顶部突出 FAIL。checks 和实际 samples 很有用，sample_rows/samples 有重复。missing clock 的 correct_example 原样保留坏路径，需修。

> 独立复核：结论正确。成功 envelope `ok=true` 与业务 `verdict=fail/all_passed=false` 并存，checks 能定位一 pass 一 fail；sample_rows/samples 重复且 handler 示例保留坏 clock，均由 raw 支持。

### `value.batch_at`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功一次返回两信号在 75ns 的值和 70/75/80ns bracket，对 edge race debug 很有用；但 values、sample_rows、samples 三套结构重复相同数据，约 5.2KB，默认应只保留 values+clock_context。summary 的 any clock edge 与 target edge 区分仍需更直白。INVALID_TIME handler 的示例是真正合法值，恢复性好。

> 独立复核：结论正确。成功返回两信号值和 70/75/80ns bracket，values、sample_rows、samples 三种表示重复同一证据；`clock_edge_hit` 与 `target_edge_hit` 区分存在但摘要仍易误读。

### `value.at`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功值为 'h22，但 summary 同时显示 clock_edge_hit=false/bracket_complete=false，clock_context 的 next_sample_time=120ns；同 fixture 同时间的 value.batch_at 返回 previous=70ns/next=80ns/bracket_complete=true，存在明显跨 action 采样上下文不一致，可能直接误导 edge debug。值事实有用，但在解释 bracket 前必须修一致性。handler 恢复信息较好并建议 scope.list/signal.resolve。

> 独立复核：结论正确。两 action 使用同一 clock/time fixture，但 value.at 给 next=120ns、bracket 不完整，value.batch_at 给 70/80ns、bracket 完整；跨 action 采样上下文不一致是会影响 edge debug 的真实问题。

### `signal.statistics`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功给 10 个 negedge sample、high=7/low=3、ratio=.7、burst 和首末变化时间，debug 价值很高且 sampling 语义完整。handler 字段定位清楚但 correct_example 通用回显坏路径的风险仍在。数据量合理。

> 独立复核：结论正确。成功 raw 给 10 个 negedge sample、7 high/3 low、0.7 ratio、burst 与首末变化时间；missing signal 精确定位 `args.signal`，但 correct_example 确实沿用不存在路径。

### `signal.stability`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功判定 stable=true、值为 1、窗口 0..200ns，并保留初始 row，debug 价值高。`transition_count=1` 与 stable=true 容易矛盾，实际是把 0ns 初值 row 当 change；应区分 change_row_count 与 actual_transition_count，参考 signal.changes 的语义。summary 为空也应补 stable/value。

> 独立复核：结论正确。成功 data 同时为 `stable=true`、值恒为 1，却把 0ns 初始 row 计作 `transition_count=1`，且 summary 为空；区分初值行与实际 transition 是必要修正。

### `signal.changes`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功声称 returned_change_rows=3/transition_count=2，并给 initial/final/first/last 和语义提示；但 data 中没有实际 changes rows，无法完成 action 最重要的“精确变化时间线”目标，debug 价值严重不足。必须返回每个 time/value row，或把 action 改名为 aggregate。handler 还把坏 signal 原样放进 correct_example。

> 独立复核：结论正确。summary 宣称 returned_change_rows=3/actual_transition_count=2，但 data 只有首末值和 first/last 时间，没有逐变化 rows；无法兑现精确时间线这一核心 debug 用途。

### `scope.list`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功列出 23 个真实信号并给 total/returned/truncated，debug 价值高，适合作为路径发现入口。不存在 scope 被定义为 ok=true 空集合，因此 handler 负例不可构造；但响应应显式 `scope_found=false`，否则用户无法区分合法空 scope 与拼错路径。默认体积合理。

> 独立复核：结论正确。正例列出 23 个信号及 total/returned/truncated；测试记录明确注明不存在 scope 被定义为空集合成功，因而无法构造 handler 失败，缺少 `scope_found` 会产生歧义。

### `sampled_pulse.inspect`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功发现 96..96.2ns 未采样 valid pulse，并给 payload 风险，核心能力很有价值；但响应约 10.7KB，first_risk 又在 findings 重复。更严重的是 truncated=true、仅 6 个 sample 后，96ns 事件仍显示 previous edge=45ns/next edge=null，后续 125..145ns payload finding 也沿用 45ns nearest edge，容易产生错误时序结论。应先修采样截断后的边界语义，再做体积优化。handler correct_example 还原样保留坏 valid path。

> 独立复核：结论正确。raw 中 first_risk 与 findings 重复，且 `truncated=true/sample_count=6` 后 96ns 事件和 125ns 以后 payload finding 仍以 45ns 为最近采样沿、next=null；该边界证据会误导时序根因判断。

### `rc.generate`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功确认文件已写、配置 valid、2 groups/4 signals，适合把证据交给 nWave，debug 价值中高；但没有列 missing/skipped signals 或产物摘要，只有计数。missing config handler 精确指 args.config_path，却把同一 missing path 放进 correct_example，必须修正。响应简洁。

> 独立复核：结论正确。成功只以 written/valid、2 groups/4 signals 和路径确认产物，没有逐信号 skipped/missing 摘要；missing config handler 指向 `args.config_path` 却把坏路径复用进 correct_example。

### `handshake.inspect`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功返回 10 samples、3 transfers、max stall=4、ready_without_valid=2、data stability violations=0；统计对协议判断有用，但没有 stall window 或 ready-without-valid 的具体时间，无法直接跳到波形现场，debug 价值中高而非完整。missing clock 能定位字段，但 correct_example 原样保留坏 clock，误导。

> 独立复核：结论正确。成功统计 10 samples、3 transfers、max stall=4、ready_without_valid=2 和零稳定性违规，但没有对应 stall/ready-only 的具体时间点；可发现异常而不能直接跳转现场。

### `expr.eval_at`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功明确表达式 true、操作数值和 before/middle/after 变化，debug 价值很高。clock_context 同时出现 clock_edge_hit=true、clock_edge_kind=posedge、目标 edge=negedge、target_edge_hit=false，字段虽足以解释但容易误读，应把摘要写成 requested_edge_hit=false/any_edge_hit=true。未知 alias handler 只说 value unavailable，不指 args.expr、不列 aliases。JSON 中 operands/sample_rows/expr_samples 有部分重复。

> 独立复核：结论正确。表达式值、操作数及 before/middle/after 均有用；同一 clock_context 的 any-edge hit 与 requested negedge miss 并存，字段可解释但摘要易误读，未知 alias 错误也缺少字段和可用 alias。

### `event.export`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功返回 2 个事件和 preview，但 data.events 与 data.preview 是逐字段完全重复的两份列表，约 6.2KB，冗余高；且 output_written=false/status=preview 时 action 名为 export，需清楚强调这是预览而非文件产物。事件证据本身很有用。未知 alias 失败恢复信息同 event.find 过弱。

> 独立复核：结论正确。成功明确 `status=preview/output_written=false`，且 data.events 与 preview 是逐字段重复的两份事件列表；事件证据有用，但 export 名称下的预览语义与冗余都应突出。

### `event.find`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功在 115ns 返回命中事件、所有 alias 值及 payload_lo 解码，clock/edge/sample point 明确，debug 价值很高。未知 alias 的 handler 仅给 ACTION_FAILED/message，无 invalid_arg、available_aliases 或正确表达式示例；应指向 args.expr 并列配置 alias。成功体积可接受。

> 独立复核：结论正确。成功事件含 115ns、全部 alias 值和 payload_lo；未知 alias 仅返回 `ACTION_FAILED`/message/cause_code，没有 `invalid_arg`、候选 alias 或合法示例，恢复性确实弱。

### `event.config.load`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功回显完整 effective config（含 reset、signals、fields），比 APB config.load 更容易核验，debug 价值高。handler 对不存在 config_path 只写 invalid_arg=args 而非 args.config_path，且 correct_example 使用 schema 中不存在/不相关的 expr 形态，恢复性差。失败三层重复。

> 独立复核：结论正确。成功回显 reset、signals、fields 等完整 effective config；missing path 只定位到 `args`，correct_example 又使用与 load 合同不符的 expr 形态，失败指导不可直接复制。

### `event.config.list`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：按 name 成功返回完整 clock/edge/sample_point 和 alias map，debug 价值高；summary 为空，应放 name/clock/edge。missing config 的 handler 有明确字段和期望，需确保提供 config.load 下一步。成功无明显冗余。

> 独立复核：部分正确。成功完整回显 name/clock/edge/sample_point/alias map 且 summary 为空的判断成立；但 missing-config handler 已明确包含 `event.config.list` 与 `event.config.load` 两条 `next_actions`，不是“需确保提供”，正确说法是该恢复提示本轮已经具备。

### `detect_abnormal`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功只报告 xz_bus 在 85ns 为 X、95ns 为 Z，值、bits、X/Z 标志都很有用；但同次请求包含明确的 glitch_sig，却没有 finding、也没有逐信号“已扫描/为何未命中/阈值”信息，无法区分无 glitch 与检测未覆盖，debug 可信度中等。handler 字段定位清楚。建议返回 scan coverage 和生效规则。

> 独立复核：结论正确。成功仅返回 xz_bus 在 85ns/95ns 的 X/Z findings，请求中的 glitch_sig 没有逐信号扫描状态、阈值或未命中原因；因此无法区分“已检查无 glitch”和“规则未覆盖”。

### `counter.statistics`

- 实测覆盖：CLI 与 MCP stdio 均完成正确、未知字段 schema 错误及 handler 语义/资源错误；除已说明的不可构造项外，code/layer 与核心 payload 一致。
- 主评审：成功返回 55..95ns、5 个有效 sample、min=0/max=4/avg=2 及首次时间，debug 价值高，足以判断计数范围与采样质量。handler 缺 clock 能精确指向 args.clock，但自动 correct_example 很可能沿用坏路径的通用问题需避免。summary/data 分工合理，冗余低。

> 独立复核：结论正确。成功明确 55..95ns、5 个有效样本、min/max/avg=0/4/2 及首次时间，足以支撑计数调试；missing clock 精确定位但 correct_example 的确保留坏 clock。

### `list.export`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功写出 u64bin.v1，返回 2 signals、6 rows、manifest 和每信号文件/width/row count；missing list 为 `LIST_NOT_FOUND`。Debug 价值中高：适合把一组波形交给离线工具，并给足 manifest 证据确认产物完整。默认响应不嵌入二进制数据，体积合理。handler 提供 create/show 下一步。需确保输出 path 的覆盖/冲突策略在错误中清楚，但本轮未触发。主评审结论：输出契约简洁有用。

> 独立复核：结论正确。两入口成功均报告 u64bin.v1、2 signals、6 rows、manifest 和逐信号文件信息，未嵌入二进制正文；missing list 有 create/show 恢复建议，产物证据简洁实用。

### `list.value_at`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功在 100ns 返回两个信号值、before/middle/after 三点、clock edge 命中和 bracket 完整性；missing list 为 `LIST_NOT_FOUND`。Debug 价值很高：同一采样边界比较多信号，且明确 90/100/110ns 上下文，可避免 edge race 误判。JSON 同时用 values、sample_rows、samples 三种形态重复同一六个值，体积明显偏高；默认保留 values+clock_context，三点细节放 verbose 即可。失败恢复信息好。主评审结论：能力强，但成功 JSON 有结构性重复。

> 独立复核：结论正确。成功在 100ns 返回两信号及 90/100/110ns bracket，直接支持多信号边界比较；values/sample_rows/samples 对同一值证据重复，结构性冗余判断成立。

### `list.validate`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功返回 all_found=true，并逐信号列 status=ok；missing list 为 `LIST_NOT_FOUND`。Debug 价值高：能在批量采样前确认所有路径仍存在，逐条状态足够定位坏成员。失败提示 create/show，恢复性好。成功 summary/data 分工合理，冗余低。主评审结论：清晰、可操作。

> 独立复核：结论正确。成功给 all_found=true 并逐信号列 status，missing list 为 handler 层 `LIST_NOT_FOUND` 且有 create/show 下一步；该结果能在批量查询前可靠检查成员。

### `list.diff`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功只返回 `diff_found=true,diff_time=55ns`；missing list 为 `LIST_NOT_FOUND`。Debug 价值偏低到中：知道首次差异时间，却不知道是哪几个信号、各自 before/after value，无法直接判断差异原因，仍需再调 value/changes。应至少返回 changed_signals 和首差值对。失败恢复信息好。成功很短，不冗余，而是信息不足。主评审结论：定位时间有用，但缺少差异主体和值是主要短板。

> 独立复核：结论正确。成功只返回 `diff_found=true,diff_time=55ns`，没有变化信号及 before/after value；可定位首次差异时间但不能解释差异主体，信息不足而非冗余。

### `list.show`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功列出 one-based index 与完整 signal path，并给 signal_count；missing list 为 `LIST_NOT_FOUND`，带 create/show 下一步。Debug 价值高，是维护 list 和按 index 删除的关键事实入口。成功信息无明显冗余；失败正确示例仍在 data/error 重复。主评审结论：清晰实用，默认形态合适。

> 独立复核：结论正确。成功包含 one-based index、完整路径和 signal_count，能直接支撑按 index 删除；missing list 的 code、层级和下一步明确，仅失败示例在 data/error 重复。

### `list.delete`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功均回显 list、removed signal 和 deleted=true；不存在的成员为 `PRECONDITION_FAILED` / handler。Debug 价值中高，能确认删掉的精确条目。失败精确指向 `args.signal`，说明可按 one-based index 或 exact signal 删除，并建议 `list.show`，可恢复性好。需要明确 index 的 1-based 合同是否也在 schema/help 中一致。冗余低。主评审结论：信息直接可用。

> 独立复核：结论正确。成功精确回显 removed signal 与 deleted=true；不存在成员为 handler 层 `PRECONDITION_FAILED`，字段、one-based/exact 期望和 list.show 建议均存在，响应低冗余。

### `list.add`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功均返回 list、signal、added/status；不存在 list 为 `LIST_NOT_FOUND` / handler，schema 未知字段被精确拒绝。Debug 价值中高：能确认具体信号已加入，信息刚好够用。handler 提供 `list.create/list.show` 下一步和合法示例，恢复性好。成功无明显冗余；失败三层重复。主评审结论：返回清晰且实用，是 list 状态动作中较好的一个。

> 独立复核：结论正确。成功返回 list/signal/added/status，missing list 为 `LIST_NOT_FOUND` 并给 create/show 下一步；两入口核心 payload 一致，debug 状态确认充分。

### `list.create`

- 实测覆盖：正确、未知字段 schema 错误、schema 合法 handler 失败均分别经 CLI 与 MCP stdio 直调；两入口核心 payload、code 和 layer 一致。
- CLI/MCP 成功均明确返回 name、created/status；重复名称为 `PRECONDITION_FAILED` / handler，未知字段为 schema。Debug 价值中等：它只证明容器创建，不回显实际初始 signals，无法确认请求中的两条信号是否都入表；应返回 signal_count 或 signals，或提示 `list.show`。handler 能指向 name 和“必须为新名称”，但无 list.show/list.delete 等冲突处理建议。响应简洁，冗余主要在通用失败三层重复。主评审结论：可用但成功证据偏弱，优先回显初始成员计数。

> 独立复核：结论正确。请求含两条初始 signal，但成功仅返回 name/created/status，data 为空，无法单凭响应确认成员是否全部入表；重复名错误虽定位 name，却没有冲突处理 next action。

### `cursor.list`

- CLI/MCP 正确场景均列出两个 cursor、active cursor 和总数；schema 未知字段正确被拒绝。该 action 无参数，空 store 也是合法成功，本轮无法诚实构造 action-handler 失败，两入口均标记 `NOT_CONSTRUCTIBLE`，不拿 session/wrapper 错误冒充。
- Debug 价值：高，名称、时间和 active 状态足够支持后续 get/use/delete。summary 为空导致 cursor_count/active_cursor 只能深入 data 查，应提升这两个字段。
- 冗余度：中。表格中的空 note/clock 和 raw epoch timestamps 占据大量列，默认可隐藏；名称、时间、active 已足够。
- 主评审结论：action 本身实用；handler 负例不可构造是接口语义事实，不算覆盖失败。优先精简默认列并补摘要。

> 独立复核：结论正确。两入口均列两个 cursor、active_cursor 和 cursor_count，summary 为空且 cursor 对象含空 note/clock 与 epoch；记录也明确 handler 负例为不可构造，而非覆盖遗漏。

### `cursor.delete`

- CLI/MCP 正确场景均返回 `status=deleted,name=mark_delete`；schema 未知字段被拒绝；删除不存在名称为 `PRECONDITION_FAILED` / handler。
- Debug 价值：中等，动作结果确定且无歧义；summary 仍为空，至少应回显 deleted/name。
- 失败质量：能指出具体名称不存在，但缺少 `invalid_arg` 和 `cursor.list` 建议。对删除类动作还应明确是否幂等；当前不存在即失败，响应没有说明这一合同。
- 冗余度：低。
- 主评审结论：结果简洁可用；补 summary、幂等语义和恢复提示即可。

> 独立复核：结论正确。成功只在 data 返回 name/status，summary 为空；不存在名称为 `PRECONDITION_FAILED`，message 可辨识但无 `invalid_arg`、list 建议或幂等说明，恢复性判断准确。

### `cursor.use`

- CLI/MCP 正确场景都返回 `status=active`、active cursor 和 `110ns`；schema 负例落在 schema；不存在 cursor 为 `PRECONDITION_FAILED` / handler。
- Debug 价值：中高，成功结果明确证明当前交互锚点已经切换。summary 为空不合理，`active_cursor/time` 应成为摘要。
- 失败质量：只给字符串式 CURSOR_NOT_FOUND，没有字段路径、可用名称或 list/set 建议；agent 仍需猜下一步。
- 冗余度：低到中，cursor object 中空 note/clock 和 epoch 可按需输出。
- 主评审结论：状态变更清楚，但失败恢复信息和 summary 需要补强。

> 独立复核：结论正确。成功 data 明确 active cursor、110ns 和 status，summary 为空；不存在 cursor 只有字符串式 CURSOR_NOT_FOUND，没有字段路径、候选名或 list/set 建议。

### `cursor.get`

- CLI/MCP 正确场景都返回命名 cursor 的 `100ns`、origin 和 timestamps；schema 负例正确落在 schema；不存在 cursor 的 handler 负例为 `PRECONDITION_FAILED`。
- Debug 价值：中高，能把对话里的命名锚点还原为确定时间。但 summary 为空，建议至少返回 name/time；空 note/clock 和 raw epoch timestamps 默认价值低。
- 失败质量：message 能说明哪个 cursor 不存在，但没有 `invalid_arg=args.name`、期望或 `cursor.list/cursor.set` 下一步，恢复性明显弱于 config 类 action。
- 冗余度：低到中；主要噪声是空字段和 epoch。
- 主评审结论：可用，但应强化 missing cursor 的结构化恢复提示，并把 name/time 提升到 summary。

> 独立复核：结论正确。成功 cursor 对象含 100ns/origin/epoch 但 summary 为空；missing cursor 为 handler 层 `PRECONDITION_FAILED`，确实缺少 `invalid_arg`、期望和下一步。

### `cursor.set`

- 实测请求：正确设置 `mark_new=100ns`；schema 负例在合法请求中加入未知字段；handler 负例传入 schema 合法但不可解析的 `time=not-a-time`。
- CLI/MCP stdio：成功均返回 cursor、resolved time 和 `status=set`；schema 均精确拒绝未知字段；handler 均为 `INVALID_ARGUMENT` / `handler`，指向 `args.time`。
- 正确返回的 debug 价值：中高。明确保存后的名称、标准化时间、origin 和状态，足以作为后续窗口/比较锚点。顶层 summary 为空，关键 `status/time/name` 全藏在 data；建议 summary 至少包含这三项。`created_at/updated_at` 是无单位 epoch 数字，对一般 debug 无用且不易读，默认可省略或格式化。
- 失败信息：message 与 expected 清楚列出 `10ns/100ps/max`，但 `correct_example` 原样保留错误值 `not-a-time`，复制后必然再次失败，并夹带本机 FSDB 绝对路径；这不是正确示例，应生成真正合法的 `time`。
- 冗余度：成功体积可接受，但 timestamps 偏噪；失败的 summary/data/error 重复且错误示例无效。
- 主评审结论：状态写入能力可用；优先修正 handler 的“正确示例”，其次补有用 summary、清理 epoch 元数据。

> 独立复核：结论正确。成功返回标准化 100ns 与 status 但 summary 为空、epoch 偏噪；不可解析时间正确到 handler 层，却把 `not-a-time` 原样放入 correct_example，复制仍失败。

### `stream.export`

- 实测请求：正确场景导出 `ready_stream` transfer 到 TSV，窗口 `0..250us`，请求同时带 `line_limit=5`；schema 负例缺失 stream；handler 负例使用未加载 stream。
- CLI/MCP stdio：均成功写出 15059 rows，并返回 output path、meta path、format、状态及完整协议统计；两类失败一致。实查 TSV 为 15060 行（含 header），不是 5 行。
- 正确返回的 debug 价值：高。输出列包含 cycle/time、transfer/stall、vld/rdy/bp、packet flags、channel id 和解码 fields，适合离线过滤与跨事务分析；返回明确确认文件实际写入和 row count。
- 关键问题：请求带 `line_limit=5`，响应同时显示 `row_count=15059`、`line_limit=5`、`truncated=false`，实际文件也写出全部 15059 行，但没有解释 line_limit 只限制什么。用户极易以为文件只会导出 5 行。若 export 有意忽略 line_limit，应从 schema 移除或返回 `line_limit_scope=response_preview`；若应限制文件，则当前行为不符合直觉合同。
- 失败信息：handler 对 missing stream 和 list/load 下一步清楚；schema 仍有同值 `did_you_mean`。成功 summary 又携带 first/last transfer/stall 的完整 payload，export action 默认只需统计与文件 manifest，当前过于冗长。
- 冗余度：高。文件导出已承载全量数据，响应无需再嵌入四个大型样本；失败仍三层重复。
- 主评审结论：导出文件本身对 debug 很有用；最高优先级是澄清或修正 `line_limit` 的实际作用，其次精简成功 summary。

> 独立复核：结论正确。两入口均报告写出 15059 rows，实测文件含 header 共 15060 行，而请求 line_limit=5、truncated=false；line_limit 作用不清且 summary 还嵌入四个大样本，问题直接影响可预期性和体积。

### `stream.query`

- 实测请求：正确场景查询 `ready_stream` 的 `first_transfer`，窗口 `0..250us`；schema 负例缺失 stream/query；handler 负例使用未加载 stream 和合法 `query=summary`。
- CLI/MCP stdio：成功均命中 cycle 7 / `75ns` 的首笔 transfer，并给出 vld/rdy、channel id 及 addr/data/is_wr/low8 解码字段；失败 code/layer 和修复示例一致。
- 正确返回的 debug 价值：很高。目标 row 同时保留采样时间、握手状态和已解码业务字段，能直接回答“第一笔任务是什么”；summary 的 transfer/stall/XZ/stability 统计也能提供背景。
- 关键问题：针对单行 `first_transfer` 查询，summary 又完整嵌入 first/last transfer、first/last stall 和所有字段，而 `data.row` 再重复 first transfer，返回远超目标所需；`truncated=true` 对单点 query 也没有解释到底截断了扫描明细还是目标结果。默认响应应把 stream 语义与核心计数留在 summary，目标 row 只放 data；首末四个大对象改到 verbose/summary query。
- 失败信息：handler 的 missing stream 与 config.list/load 下一步很清楚；schema 的同值 `did_you_mean=args.stream` 仍无意义，并忽略同时缺失的 query。
- 冗余度：高，是本轮已看 action 中成功响应最明显的冗余之一；同一首笔 transfer 在 summary 和 data 完整重复。
- 主评审结论：debug 能力本身非常强，但默认输出需要按 query 类型裁剪；否则大量上下文会稀释真正命中的 row，并增加 agent token 成本。

> 独立复核：结论正确。first_transfer 命中 cycle 7/75ns 并含业务字段，debug 价值高；同一 row 又完整出现在 summary.first_transfer 与 data.row，且 truncated=true 未说明作用域，冗余与语义风险均有依据。

### `stream.validate`

- 实测请求：正确场景对 `ready_stream` 做 dynamic validate，窗口 `0..250us`；schema 负例缺失 stream；handler 负例使用未加载 stream。
- CLI/MCP stdio：成功均为 `summary.ok=true`、`issues=[]`，并返回 20011 个 clock edges、15059 次 transfer、3764 个 stall cycle/window、首末 transfer/stall、XZ/conflict/stability 计数；两类失败一致。
- 正确返回的 debug 价值：很高。它不仅验证 signal/表达式配置可用，还提供动态协议健康概览和首末异常现场，可直接决定下一步查 transfer、stall、XZ 还是 stability。`dynamic.truncated=true` 与顶层 `summary.ok=true` 同时出现却没有解释“截断的是明细还是验证覆盖”，存在把部分验证误读为全量通过的风险；应增加 `validation_complete`、`scanned_range` 和 `truncation_scope`。
- 失败信息：handler 的 missing config、字段定位、list/load 下一步都清楚。schema 仍生成无意义的同值 `did_you_mean=args.stream`，与 `stream.show` 同问题。
- 冗余度：正确 JSON 偏大，但这些统计和首末证据对 validate 有实际价值；可把完整 field payload 放 detail/verbose，默认保留时间、cycle、transfer/stall 和异常计数。失败三层重复仍偏高。
- 主评审结论：属于高价值 bring-up/健康检查 action；最高优先级是澄清 truncated 与 `ok=true` 的覆盖语义，避免假阳性理解。

> 独立复核：结论正确。summary `ok=true`、issues 为空，但 dynamic 同时 `truncated=true` 并含 20011 edges/15059 transfers 等统计；没有 validation_complete/scanned_range，可能把部分覆盖误读为全量通过。

### `stream.show`

- 实测请求：正确场景显示 `ready_stream`；schema 负例缺失 stream 并带未知字段；handler 负例使用未加载 stream 名。
- CLI/MCP stdio：成功都返回完整 signal alias map、clock/edge/sample point、reset、vld/rdy 表达式、data fields、channel id、interleaving、issues 和 transfer/stall semantics；两类失败的 code/layer 一致。
- 正确返回的 debug 价值：很高。它完整回答“这个抽象流到底绑定了什么、在哪个沿采样、何时算 transfer/stall、payload 如何解码”，足以在 query 前人工审查配置，且没有塞入动态波形统计，职责边界清楚。
- 失败信息：handler 路径质量高，精确指向 `args.stream`，并给出 config.list/load 的下一步。schema 错误里 `did_you_mean=args.stream` 与缺失字段本身完全相同，message 也变成“缺少 stream；请使用 stream”，没有新增恢复信息；真正随请求出现的未知字段反而未报告。缺失字段时不应生成同值 `did_you_mean`。
- 冗余度：成功结果合理，summary 是有效摘要、data 是完整定义；失败仍有三层重复。
- 主评审结论：这是配置可解释性最好的 action 之一；只需清理 schema 错误中无意义的同值 `did_you_mean` 和通用失败重复。

> 独立复核：结论正确。成功完整回显 signal map、采样语义、表达式、fields/channel 和 transfer/stall 定义，职责清楚；schema 缺失 stream 时 `did_you_mean` 与字段本身相同且未报告同时出现的未知字段。

### `stream.config.load`

- 实测请求：正确场景从真实 stream_v1 配置文件以 replace 模式加载 7 个 stream；schema 负例只传未知字段；handler 负例传不存在但类型合法的 config path。
- CLI/MCP stdio：成功均返回 `loaded=7`、7 个 stream 名称，并报告 `valid_only` 的 `CLOCK_COMPLEX` warning；schema 均为 `INVALID_REQUEST` / `schema`，handler 均为 `INVALID_ARGUMENT` / `handler`。
- 正确返回的 debug 价值：中高。加载数量、实际名字和语义 warning 都直接有用；`CLOCK_COMPLEX` 明确说明 edge detection 会依赖表达式依赖项变化，能提前暴露采样风险。没有回显每个 stream 的 effective config 是合理的体积折中，因为可用 `stream.show` 精查；但成功结果应给出明确的 `next_action: stream.validate/show`，让 agent 知道 load 成功不等于信号均可解析。
- 失败信息：schema 对未知字段的定位非常准确，包含 `additionalProperties` 约束和完整合法配置示例。handler 说明文件不存在，也列出四种合法输入来源和最小 inline 示例；但 `invalid_arg` 只写 `args`，实际应精确到 `args.config_path`。
- 冗余度：中高。完整 stream schema 示例很长，且在失败 JSON 中重复；建议 summary 只保留路径和短期望，完整示例只放 error。
- 主评审结论：对 stream debug bring-up 很实用，warning 质量好；优先补 load 后验证提示，并把 handler 字段路径精确化。

> 独立复核：结论正确。成功返回 loaded=7、名称及 `CLOCK_COMPLEX` warning，足以支撑 bring-up；missing path 的 handler 仅定位 `args` 而非 `args.config_path`，长合法示例在失败结构中重复。

### `apb.transfer_window`

- 实测请求：正确场景查询 `0ns..1us`、`line_limit=20`；schema 负例缺失 name；handler 负例使用未加载配置名。
- CLI/MCP stdio：正确场景都返回 10 笔事务，首笔 `125ns WR 0x0/0x11223344`，末笔 `525ns RD 0xf0/0xbad000f0 has_error=true`；错误 layer/code 两入口一致。
- 正确返回的 debug 价值：高。时间、读写类型、地址、数据和 error 以按时间排列的窗口形式同时给出，比单笔 query 更适合还原寄存器访问序列，且这里使用带单位时间，明显优于 `apb.query/cursor` 的 raw 数值时间。缺少 `truncated`、返回条数与窗口内总条数的区分；当 `line_limit` 截断时 agent 可能把局部列表误当全量。
- 失败信息：schema 失败清楚可修复。handler 失败虽正确标为 `CONFIG_NOT_FOUND` 并指向 name，但 `correct_example` 原样复用了不存在的 `missing_config_for_handler_test`，复制后仍会失败；也没有像稳定 APB actions 那样给出 config.list/load 的 `next_actions`。这是明显的恢复性缺陷。
- 冗余度：成功结果合理；失败仍在 summary/data/error 重复。handler 返回还把 fixture 的本机绝对 FSDB 路径放进示例 target，既冗长，也不适合作为可复制的通用建议。
- 主评审结论：窗口证据对 debug 很有用；优先修复 handler 的错误示例和 next action，再补截断语义。

> 独立复核：结论正确。成功返回 10 笔带单位、按时序排列的 APB 事务及 error 标志，但没有总数与截断区分；missing config 的 correct_example 复用坏 name，且缺少 config list/load next action。

### `apb.cursor`

- 实测请求：正确场景对已加载 APB 配置执行 `op=begin,direction=all`；schema 负例缺失 name/op；handler 负例使用不存在的配置名但保留合法 op。
- CLI/MCP stdio：正确场景均找到首笔 write，地址 `00000000`、数据 `11223344`、`has_error=false`；schema 均为 `INVALID_REQUEST` / `schema`，handler 均为 `CONFIG_NOT_FOUND` / `handler`，核心返回一致。
- 正确返回的 debug 价值：高。一次调用就把 cursor 操作和落点事务绑定，适合交互式前后浏览 APB 访问。缺陷有两点：事务 `time=125000` 没有单位；返回没有 cursor 当前序号/总事务数，用户无法判断“当前位置”和距离边界还有多远。建议至少返回标准时间字符串、1-based index 和匹配总数。
- 失败信息：schema 错误可直接修复；handler 错误准确指向 `args.name`，并建议 list/load 配置。MCP 示例壳转换正确。未知字段与缺失必填同时存在时仍只报告首个缺失字段。
- 冗余度：中高，问题与 `apb.query` 相同：handler 错误的 summary/data/error 重复；成功结果的 summary 与 transaction 分工合理。
- 主评审结论：交互式 debug 价值明确且两入口一致；优先补时间单位和 cursor 位置上下文。

> 独立复核：结论正确。成功定位首笔 write 并给地址/数据/error，但 time=125000 无单位且没有 cursor index/总事务数；missing config 的字段和恢复路径清楚，两入口核心结果一致。

### `apb.query`

- 实测请求：正确场景在已加载 APB VIP 配置上查询 read、地址 `'hf0`；schema 负例缺失必填 `args.name`；handler 负例引用未加载的配置名。
- CLI：正确命中一笔读事务，返回 address `000000f0`、data `bad000f0`、`has_error=true` 和 time `525000`；schema 负例为 `INVALID_REQUEST` / `schema`；handler 负例为 `CONFIG_NOT_FOUND` / `handler`。
- MCP stdio：正确事务及两类失败与 CLI 一致；schema/handler 的 `correct_example` 都转换为 MCP tool 参数形态。
- 正确返回的 debug 价值：高。地址过滤后直接给出读写方向、地址、数据和 PSLVERR 事实，能快速定位异常 APB access；特别是本例同时返回 `has_error=true`，对 debug 决策直接有效。主要缺陷是 `data.transaction.time=525000` 没有单位，而同一 fixture 的窗口类 action 使用 `525ns`，agent 无法安全判断这里是 fs、ps 还是其它 raw tick。应返回带单位的标准时间字符串，或同时返回 `time_ticks + time_unit`。
- 失败信息：schema 错误包含字段路径、类型、schema 文件和最小示例，清晰可恢复。handler 错误不仅指出 missing config，还给出 `apb.config.list` / `apb.config.load` 两个下一步，信息质量很好；但 `data` 与 `error` 重复同一组恢复字段和完整示例。
- 冗余度：中高。成功结果的 summary 与 data 适度分工；XOUT 又重复 name/direction/found。失败结果在 summary/data/error 三层重复，完整 `correct_example` 占比过大。
- 主评审结论：这是实际 debug 很有用的 action；最高优先级问题是时间无单位，失败路径本身已达到可操作水平。

> 独立复核：结论正确。CLI/MCP 均命中地址 f0 的 read，返回 bad000f0 与 `has_error=true`，对异常访问很有用；time=525000 无单位，而 handler 的 config.list/load 建议完整，失败三层重复也属实。
