# Active Trace Bug 修复复盘：把“最近一次真实驱动”变成 AI 可直接使用的证据

## 为什么需要 `trace.active_driver`

`xdebug` 里的 `trace.active_driver` 和 `trace.active_driver_chain` 不是为了替代工程师读 RTL，也不是为了把静态 driver tracing 再包装一层。它们的核心目标更具体：让 AI 在面对一个波形异常时，用更少的工具调用、更低的推理负担，直接拿到“这个信号在这个时间点为什么变成这样”的证据链。

没有 active trace 时，AI 通常要做一串分散查询：

1. 先用 `value.at` 确认目标信号在某个时间点的值。
2. 再用 `trace.driver` 找静态 driver。
3. 再回到波形里查 RHS 信号、reset、enable、grant、select 等控制条件。
4. 再自己判断哪条 assignment 在这个时刻真正生效。
5. 如果跨 module port，还要继续查端口连接和上游信号。

这套流程的问题不是不能做，而是 AI 很容易在中间丢掉上下文：静态 driver 可能有多条，波形值可能需要精确到一次跳变，端口方向和真实边界也容易混淆。`trace.active_driver` 的设计目的就是把这些分散步骤合并成一个 action：输入一个 signal 和 requested time，输出 active time、真正 active 的 assignment/force evidence、RHS data signals、termination reason，以及必要时的一段 chain。

换句话说，这个 action 是给 AI 降维的。它把“读波形 + 查 RTL + 判断当时哪条语句生效”压缩成可消费的结构化证据，减少反复调用工具的次数，也降低模型自己推理 RTL 时犯错的概率。

## 这次遇到的问题

这次问题最开始暴露在一个很常见的 RTL 形态上：

```systemverilog
assign output_valid_cb = |grant_vector;

always @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    output_valid <= 1'b0;
  end else begin
    output_valid <= output_valid_cb;
  end
end
```

目标信号是一个 module output reg，真实数据来源是一个组合信号，而组合信号又来自归约运算。用户在波形某个时间点 query `output_valid`，期望 active trace 返回：

- active time 是目标信号最近一次真实跳变时间；
- driver 是 `output_valid <= output_valid_cb`；
- chain 下一跳能继续看到 `output_valid_cb`；
- 如果 native/NPI 无法提供 active evidence，应明确返回 unresolved，而不是假装找到了 primary input。

旧实现有两个明显问题。

第一，zero-evidence 被误解释成 primary input。`npi_active_trace_driver_by_hdl(...)` 返回 0 时，代码会进入 fallback 分支。旧逻辑只要没有 active data signals，就倾向于构造一个 `primary_input` terminal node，并把响应映射成 resolved。这对真正的 top input 是合理的，但对 module internal/output 是错误的。内部信号没有 active evidence，不等于它是 primary input。

第二，active time 可能来自 native PVC time，存在精度截断风险。我们观察到一些环境里 query `10000ns`，native 返回的 active time 类似 `9.98us` 或更粗粒度表达。它能说明“附近发生过 active event”，但不一定是 `npi_check_active_handle` 所需要的精确 statement active time。结果就是静态 driver 明明存在，active check 却可能因为时间字符串不够精确而失败，最后表现成 `unresolved` 加 `no driver evidence`。

这两个问题叠在一起，就会出现很糟糕的用户体验：要么把没有证据的 internal/output 伪装成 resolved primary input，要么明明有静态 driver 和真实跳变，却因为 active time 精度问题拿不到 active assignment。

## 我们怎么把问题拆开

修复前先做了几组实验，而不是直接改 fallback。

### 1. zero-evidence 红测

先构造 native active trace 返回 zero-result 的场景，确认旧逻辑确实会把 module internal/output 误判成 `primary_input/resolved`。这一步的价值是把“猜测中的 bug”变成稳定可复现的红测。

覆盖点包括：

- output reg 由 clocked always block 赋值；
- RHS 是组合中间信号；
- 中间信号由 reduction、bitwise、logical、ternary、concat、slice 等表达式驱动；
- primitive output；
- active trace chain 在某一跳拿不到 active evidence。

期望统一收紧为：普通 internal/output 没有 active evidence 时，结果是 `unresolved`，`driver/root_driver` 保持 null，不再伪造成 primary input。

### 2. module input 不是简单边界

另一个容易误伤的场景是用户直接 trace 子模块 input：

```systemverilog
child u_child (
  .input_port(parent_signal),
  .output_port(child_output)
);
```

从当前 handle 看，`input_port` 的 direction 确实是 input。但它不是全局意义上的 primary input，它还有上游连接 `parent_signal`。因此新的语义必须区分：

- 当前 handle 是子模块 input/inout，且存在 high/low/ref connection：继续沿端口连接追上游；
- 当前 handle 是真正外部边界，且没有上游可解析：可以终止为 `primary_input`；
- 当前 handle 是 module internal/output，且没有 active evidence：终止为 `unresolved`。

这个改动同时作用于 `trace.active_driver` 和 `trace.active_driver_chain`，避免 chain 在端口处过早停住。

### 3. active time 精度实验

之后我们专门测试“requested time 和真实跳变时间不相等”的情况。例如目标信号在 `9995ns` 跳变，用户 query `10000ns`。设计意图上，active trace 应该回答“最近一次真实 active event 是 `9995ns`，那一刻生效的是哪条 assignment”。

native API 的典型流程可以简化成：

```text
npi_get_pvc_time -> npi_trace_driver_by_hdl2/static trace -> npi_check_active_handle
```

问题在于 `npi_get_pvc_time` 返回的时间字符串精度在不同环境中不完全可靠。静态 trace 能找到候选 driver，但 active check 需要精确时间。时间一旦被格式化成更粗的单位，就可能查不到 active candidate。

因此最后的修复原则不是重写 RTL driver traversal，也不是自研 active evaluator，而是只替换“active time 来源”这一环。

## 最终修复策略

新的公共 resolver 采用下面的路径：

```text
FSDB 精确 value-change time -> npi_trace_driver_by_hdl2/static trace -> npi_check_active_handle
```

关键点有三个。

第一，不再调用 `npi_active_trace_driver_by_hdl` 作为主路径，也不再用 `npi_get_pvc_time` 作为 active time 来源。我们从 FSDB 里找目标信号在 requested time 之前或等于该点的最近一次真实 value change，并把这个时间格式化成不丢精度的字符串。

第二，static trace 仍然使用 Verdi/NPI 的 `npi_trace_driver_by_hdl2`。我们没有自己解析 RTL AST 来找 driver，因为那会引入大量语义坑：generate、parameter、interface、modport、always block、continuous assign、force、primitive 等都很容易偏离工具真实语义。

第三，active check 仍然使用 `npi_check_active_handle`。也就是说，我们没有替代 Synopsys 的 statement active 判断，只是把传给它的时间从 native PVC time 换成 FSDB 精确跳变时间。

这样修复后，`trace.active_driver` 和 `trace.active_driver_chain` 都消费同一个 resolver 结果：

- 有 active assignment/force evidence：返回 `driver_status=resolved`；
- 多个 active assignment candidate 无法唯一判断：不强猜；
- 找不到 precise time 或没有 active candidate：继续走端口上游解析；如果仍然没有证据，internal/output 返回 `unresolved`，true top input 返回 `primary_input`。

响应里也增加了诊断字段，例如：

- `evidence_source="fsdb_precise_time_static_trace"`；
- `static_candidate_count`；
- `active_check_count`。

这些字段不是为了让用户读大量内部 dump，而是为了让 AI 能知道这个结论来自哪里：是 active evidence，还是 zero-evidence fallback，还是端口边界终止。

## 修复 `trace.active_driver_chain`

chain 的 bug 和 single driver 版本同源，但表现更隐蔽。旧逻辑中，某一跳如果 `data_signals.empty()`，就可能把这一跳的 reason 直接设成 `primary_input`。这实际上把“当前 active evidence 没有 RHS 数据信号”和“当前节点是 primary input”混为一谈。

修复后，chain 的判断顺序变成：

1. 先用公共 resolver 获取当前 hop 的 active evidence；
2. 有 data signals 就生成下一跳；
3. 没有 data signals 时，检查当前 handle 是否是真实 input/inout；
4. 如果是 module input/inout，尝试沿端口连接追上游；
5. 如果是外部边界，才终止为 `primary_input`；
6. 如果是 internal/output，终止为 `unresolved`。

这样 chain 不会因为 native 没返回 statement 或 RHS，就把内部节点误报成 primary input。

## 测试如何固化

这次测试不是只补一个最小 case，而是把我们在排查中遇到的异常族固化下来。

### zero-evidence case

`active_zero_evidence` fixture 覆盖：

- clocked output reg；
- reset branch；
- RHS 中间信号；
- reduction expression；
- primitive output；
- 18 个表达式矩阵；
- module output 直接 trace；
- module input 直接 trace；
- true top input。

期望是：

- internal/output zero-evidence 返回 unresolved；
- 不再伪造 primary input；
- 子模块 input 能沿 port connection 继续追；
- 真正 top input 仍然能合法终止为 primary input。

### 精确时间 case

构造目标信号在某个精确时间跳变，而 query time 晚于跳变点。期望返回的 active time 是 FSDB 中最近一次真实跳变时间，并且 active assignment 能在这个精确时间上通过 `npi_check_active_handle`。

这类 case 验证了我们只替换 active time 来源、不替换 static trace 和 active check 的设计。

### 回归链路

核心验证包括：

```bash
python -m pytest xdebug/tests/combined/test_active_zero_evidence.py -q
python -m pytest xdebug/tests/combined/test_active_semantics.py -q
make -C xdebug combined-test
make full-test PYTHON=python3
```

后续又因为 `xif_agent` 包名从 `xif_types_pkg` 改为 `xif_pkg`，顺手修复了 xif event fixture，并暴露出 engine 侧 `event.config.load` 对旧字段切片写法不兼容的问题。这个不是 active trace 主线 bug，但属于同一次回归清理中发现的真实兼容性问题，也已经修掉。

## 这次修复的边界

这次没有做三件事。

第一，没有实现完整 RTL event evaluator。我们不自己判断哪条 if/case branch 在某个时刻成立，而是继续交给 `npi_check_active_handle`。

第二，没有自研 static trace。driver candidate 仍然来自 `npi_trace_driver_by_hdl2`，保持和 Verdi/L1 语义一致。

第三，没有把所有 no-driver 场景都“补成 resolved”。找不到 active evidence 时，正确答案有时就是 unresolved。这个状态比假 resolved 更有价值，因为它告诉 AI：这里不要继续基于伪证据推理。

## 最终效果

修复后的 active trace 语义更窄，但更可信：

- `primary_input` 只表示真实外部边界；
- module input 会优先沿端口连接追上游；
- internal/output zero-evidence 不再被伪装成 resolved；
- active time 来自 FSDB 精确跳变时间；
- driver evidence 来自 static trace candidate 加 active check；
- chain 和 single driver 共用同一套 resolver，避免行为分叉。

对 AI 来说，这意味着一次 `trace.active_driver` 可以给出更直接的因果证据；一次 `trace.active_driver_chain` 可以沿着真实 active data path 走下去；遇到工具无法证明的地方，也会明确停在 unresolved，而不是给出一个看似顺滑但错误的故事。

这就是这个 action 最重要的价值：不是让输出看起来更完整，而是让 AI 在更少的工具调用里拿到更可靠的证据，并知道什么时候应该停止推理。

## 生图提示词

一个调试系统的概念图：左侧是 AI 助手面对波形异常，桌面上散落着多个工具查询卡片，包括 value query、static driver、wave cursor、port connection；中间是一条收束的 active trace 管线，输入为 signal 和 requested time，管线内部依次标出 FSDB 精确跳变时间、static driver candidates、active check、port connection follow；右侧输出一条清晰的因果链，节点包括 target signal、clocked assignment、RHS signal、upstream expression、external boundary；图中对比一条红色虚线错误路径，把 internal output 误指向 primary input，旁边有 unresolved stop 标记；整体突出“减少工具调用”“降低推理难度”“只保留可验证证据”的关系。
