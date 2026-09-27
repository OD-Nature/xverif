# 原生 coverage 维护复审与收敛（2026-09-27）

## 判断依据

本次基于上游 681836d13b717aa74fffe2885d44ff800a6db430 与自有分支的
b5618c45、dc65ca1d、01f63e71 三个提交进行复审。作者意图仅引用提交记录，
不把本机失败推断为作者故意限制功能，也不把本机通过外推到所有 EDA 安装。

| 项目 | 性质 | 决策 |
|---|---|---|
| 移除 xeda-runner | 上游主动停止维护该执行路径 | 保持移除，项目使用既有执行入口 |
| URG 负责读取、NPI 负责排除 | 上游架构选择 | 保留，不恢复全树 NPI 汇总 |
| ConfigOpt 缺失 | Python binding 能力差异；原实现访问属性早于能力检查 | 保留直接使用原生 strict API 的实现 |
| FSM/条件/分支/断言漏读、cross 漏报 | xverif 解析及完整性检查缺陷 | 保留确定性修复与反例测试 |
| 自动 bin 范围粒度 | 原生接口边界 | 保留范围身份，不扩大单 bin 排除 |
| EL 卸载缓存、line CSV、modport 追踪 | 状态/格式/语义缺陷 | 保留修复与往返验证 |
| 加载及关闭时原生崩溃 | 当前厂商运行库组合中观察到的故障 | 保留进程隔离，明确规避措施的适用边界 |
| 初始化网络等待 | 站点环境问题 | 网络策略留在站点；工具只负责有界等待、诊断与回收 |

上游删除执行器的依据为 1d52a93c；旧 Python 接口 strict 能力限制的意图见
cdae29a9。缺少 Python ConfigOpt 不等于原生 EDA 不支持 strict。

## 本次改变及理由

1. 撤销 worker 对所有机器强制设置 VCS_USE_MALLOC=1 的行为。
   默认继承站点环境；只有显式配置 XVERIF_XCOV_NATIVE_USE_MALLOC=0/1 时才覆盖
   coverage 子进程的分配器选择。非法配置在启动前报 NPI_ALLOCATOR_INVALID。
   不修改父进程、URG、VCS 或 xdebug 的分配器环境，不自动探测或 fallback。
   已验证需要系统分配器的机器在仓库外启用该选项。
2. 将 CSV 纯格式测试与真实 exclusion 测试拆开，真实用例归入 xcov.exclusion_npi。
   将 MCP 真实 coverage 用例拆入 xverif_mcp.coverage_real。普通 xcov.unit 和
   xverif_mcp.process 无 VDB fixture/NPI 依赖。原 20 个 exclusion 测试和 42 个
   SDK smoke 测试均保留且只登记一次；增加 catalog 依赖边界门禁。
3. 增加分配器未设置、继承、显式覆盖、非法值及父环境不变的测试。
   增加重复读取的状态一致性、RSS 观察和进程回收测试。内存数值属于观测数据，
   不把固定小样本的结果伪装成任意规模上限。
4. 保留独立 worker、严格排除、超时终止、不自动重放 mutation 和父进程死亡清理。
   默认 init 仍为 120 秒；站点 30 秒配置不进入共享默认。
5. 永久句柄和 close/end 后直接退出仍作为当前分支的明确策略保留。
   不在缺少厂商根因修复证据时重新启用曾崩溃的析构路径，也不增加旧 binding 后端。

## 风险和使用边界

- release 仅注销 RPC ID，原生句柄由整个会话持有。不同对象持续增长的长会话仍可能
  占用更多内存；调用方应显式保存 CSV/EL，并在任务边界关闭。
- 进程退出回收 OS 资源不等于对所有许可证服务器归还时序的保证；现场日志只是
  当前安装的观测证据。生产规模和其它 Verdi 安装需独立验证。
- 新 Python wrapper 与 native worker 必须配套部署；不提交厂商文件、原生二进制、
  容器配置、代理策略或许可证内容。
- 共享仓库不提供“自动重试直到通过”，也不把环境未满足的测试计为成功。

## 验证记录

首轮关联回归：510 passed、3 failed、3 skipped。两个失败来自测试启动环境未将
xcov 加入子进程 PYTHONPATH；另一个来自真实 guide 测试未绑定当前工作树，继承了站点旧 XVERIF_HOME；
当前工作树前端最初也尚未构建。
已在当前工作树构建前端并补齐环境；首轮失败记录保留，不解释为功能通过。


第二轮：513 passed、1 failed、3 skipped，唯一失败仍是 guide 的旧 XVERIF_HOME。
最终将该真实测试显式绑定本工作树；MCP process suite 复验为 217 passed、3 skipped。
其余 297 个关联用例在第二轮通过，合计覆盖 514 个通过用例、3 个环境跳过；
这是分轮验证结果，不是一次全量通过。另将 Verdi/VCS、许可证及分配器变量移除后，
xcov.unit 的 194 个用例全部通过，确认纯格式/契约测试不需要 EDA fixture。

有界资源观察（Linux / Verdi V-2023.12-SP2，站点显式启用系统分配器）：
- 正式 exclusion fixture 连续 20 次读取，每次 81 行，RSS 从 112536 KiB 到
  112656 KiB；首轮增长 120 KiB 后稳定，关闭后 worker 已回收。
- 实际 UART1 DUT line 连续 10 次读取，每次 1460 行，7.89 秒；RSS 从
  114500 KiB 到 115468 KiB，累计增长 968 KiB，后续轮次仍有数十 KiB 增长。
  关闭后 worker 已回收。此结果验证了当前规模的可用性，也确认不能宣称长会话零增长。
- 上述 UART 观察窗口中 Verdi OUT=1、IN=1、DENIED=0；仅记录计数，未复制许可证/账号内容。

最终公共文档与两个受影响 skill 的合同检查共 28 项通过。

原始日志、数据库与 RSS 逐轮数据保存在本机 ignored work，不进入公共仓库。
真实 SSH 因未配置 localhost 免密登录保留跳过；未测试真实 LSF 集群和其它 Verdi 安装。
