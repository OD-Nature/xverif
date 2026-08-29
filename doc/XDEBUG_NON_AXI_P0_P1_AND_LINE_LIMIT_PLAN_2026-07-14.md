# xdebug 非 AXI P0/P1 优化与 `line_limit` 全量收口计划

## 目标

修复 XDTE 反馈中仍存在的非 AXI P0/P1 问题，并全量收口公开 Action 的
`line_limit` 合同。实现必须保持单次主扫描、缓存数据库优先、严格 schema 和
现有 XOUT 冒号对齐风格。

## P0：正确性与限制合同

- `line_limit` 只限制 response/XOUT 行数；新增 `max_samples` 作为显式采样扫描
  预算，新增 `max_events` 作为 `event.export` 文件与聚合输入预算。
- 修复 `window.verify`、`counter.statistics`、`signal.statistics` 把
  `line_limit` 当扫描上限的问题；聚合结论不得随返回行数变化。
- `event.find(all)` 完整统计并只返回前 N 条；`first/last` 不接受
  `line_limit`，其中 `last` 必须返回窗口真正最后命中。
- `event.export` 分离响应预览、文件/聚合事件预算和采样预算，并正确报告不完整性。
- 删除或拒绝无意义、条件不适用的 `line_limit`，禁止接受后静默忽略。
- `list.diff` 改为返回窗口内首个真实 value-change 及同刻全部变化信号，不再用
  `diff_time-1 tick` 推测前值。
- `handshake.inspect` 默认检查 stall 期间 VALID 保持，报告
  `valid_dropped_before_handshake` 和独立 unknown 状态。

## P1：证据、可读性与性能

- `sampled_pulse.inspect` 分开统计漏采 valid 与 payload 风险；payload finding
  默认仅汇总，可选 `off|summary|all`。
- `scope.list` 增加全路径 glob `name_pattern` 和 `kind`，流式过滤并区分扫描、
  响应和 XOUT 渲染截断。
- active trace 保留 `termination`，新增机器可读 `termination_detail`。
- `signal.resolve/canonicalize` 建立 design-side 静态 port connectivity component；
  canonical 选择最浅非 port 父层 net，波形等价明确为未验证。
- Stream 分析完整扫描，但按 query 有界保留返回证据，缓存规模不随总 transfer 数增长。

## 缓存优先验证

- 优先复用已发布的 `xdebug.ai_complex_wave`、`xdebug.stream_v1`、
  `xdebug.active_semantics`、`xdebug.active_zero_evidence`、
  `xdebug.interface_port_root`、`xdebug.design_uart` 和 `xdebug.design_p3`。
- 不修改 fixture 源码，不主动运行 `--xverif-prepare all-generated`，普通 gate 只消费缓存。
- cache miss 或 fingerprint mismatch 时不自动 prepare、不 fallback；先确认原因，确需生成时
  再申请仅准备单个 fixture。
- 开发阶段增量构建和 focused suite；稳定后只做一次 clean build，再跑 fast gate 与 host
  regression。所有 NPI/FSDB/VCS 测试在沙箱外执行。

## 验收

- 所有声明 `line_limit` 的 Action 都有明确适用模式和实现，静态门禁禁止将其直接传给
  clock scanner。
- 小/大 `line_limit` 下聚合结果一致；预算耗尽时完整性和 verdict 准确。
- window/counter/signal statistics/handshake/pulse 每次请求最多一次主扫描；event last 使用
  常量证据空间；Stream 证据缓存受 `line_limit` 约束。
- JSON、schema、examples、XOUT、CLI/README、xverif skill reference 和
  `doc/agents/xdebug` 同步通过门禁。

## XOUT 返回风格示例

新增字段继续使用现有 `TextResponseBuilder`，同一 section 内按最长 key 对齐冒号：

```text
@xdebug.handshake.inspect.v1
summary:
  transfer_count                       : 4
  require_valid_hold_until_handshake   : true
  valid_hold_violations                : 1
  returned_finding_count               : 1
  analysis_complete                    : true
  response_truncated                   : false
```

JSON 中的 `truncation_scopes` 保留机器可读数组；XOUT 默认只渲染摘要标量和受
`line_limit` 控制的证据表，不展开无界 payload。
