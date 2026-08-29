# xdebug P2：APB、Stream 与 Action Catalog 收口计划

本计划把 XDTE 反馈中剩余的三个 P2 项放在一次实现中完成，但严格按阶段验收：

1. APB query 默认查询全方向，并明确无 `PREADY`/`PSLVERR` 时的分析假设。
2. Stream 全面采用 packet 语义命名，区分完整包与窗口边界半包，并补静态预检。
3. Action catalog 增加 `category`、`requires`、`purposes` 和双语关键字搜索；不提供 status 过滤。

## 阶段一：APB

- `apb.query.direction` 接受 `read/write/all`，默认 `all`。
- `all` 的 index、last、line limit 和 address filter 都基于全局握手时间序列。
- summary 返回总数、读数、写数和有效方向。
- config load/list 返回无 `PREADY`、无 `PSLVERR` 时的结构化假设。
- 必须复用现有 analyzer cache，不增加第二次 FSDB 扫描。

## 阶段二：Stream

- `stable_fields` 全 surface 重命名为 `packet_stable_fields`，不保留 alias。
- `field_scope=stable` 改为 `packet_stable`，warning 和导出列同步改名。
- 删除 `packet_count`，返回 `complete_packet_count`、`partial_packet_count` 和
  `packet_count_status=exact|not_configured|ambiguous`。
- config load/show 返回 alias、requested/resolved path、width、sampling 和 packet rule 预检。
- 预检只做 signal property 查询；packet 计数复用现有单次分析循环。

## 阶段三：Action Catalog

- `actions.yaml` 作为双语描述、`purposes` 和用途说明的唯一事实源。
- 每个 action 可同时拥有多个 `purposes`；固定集合为
  `discover/configure/query/inspect/analyze/trace/verify/export/manage/transform/orchestrate`。
- `actions.args.filter` 只提供 `category`、`requires`、`purposes` 和 `keyword`；
  明确拒绝 `status`。
- keyword 搜索 action name、英文描述和中文描述。
- schema 标准 `description` 使用英文，`x-description-zh` 使用中文。
- runtime 使用生成的内存 metadata，搜索时不逐个读取 schema 文件。

XOUT 保持现有块级渲染风格，同一块内冒号按最长字段对齐。例如：

```text
@xdebug.actions.v1
summary:
  action_count      : 2
  total_action_count: 70
  removed_count     : 1
  verbose           : true
  filtered          : true
```

## 验收约束

- 每阶段 focused suite 通过后才进入下一阶段。
- NPI、FSDB、VIP、MCP 测试全部在沙箱外运行并消费缓存。
- cache miss 时停止并报告 prepare 命令，不自动仿真、不切换数据源、不降级。
- 最终执行完整构建、regression、skill suite、skill 安装和镜像 diff。
