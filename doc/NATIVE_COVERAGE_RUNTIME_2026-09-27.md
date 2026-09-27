# 原生 coverage 与驱动追踪修复记录

日期：2026-09-27。

本分支以 `681836d13b717aa74fffe2885d44ff800a6db430` 为基线，将本地验证过的
xverif 修复纳入 OD-Nature/xverif 的源码历史。它包含实质性的 coverage 后端变更，
并非未修改的上游发行版。后续修改、审查和构建应以此仓库为准。

## 动机和范围

- 同一 Verdi V-2023.12-SP2 安装的 Python coverage binding 未暴露 `ConfigOpt`，
  但原生 C API 支持 strict exclusion。新增 C++ worker，直接使用
  `npiCovExclusionInStrictMode`，不保留旧 Python 签名兼容分支。
- 原生 worker 独占 NPI 上下文，通过 socketpair/JSON 传递请求和会话内对象 ID；
  Python 端检查句柄归属。worker 故障明确返回 `NPI_WORKER_LOST`，不自动重启、
  重开数据库或重放排除操作。
- 修复卸载 EL 后 URG 排除引用与汇总缓存未清除的问题；修复 line gap CSV 写入
  非法 object/bin 的问题，并在发布前校验 CSV。
- 根据真实 NPI connectivity 展开 interface/modport 的驱动候选，避免将声明节点
  当作最终驱动，并限制重复展开。
- x-npi coverage helper 使用同一原生 worker；同步 skill、构建规则和相关测试。
- Fake LSF 故障测试等待会话打开后终止明确的子进程，移除固定延时造成的竞态；
  MCP coverage 测试改用正式 catalog fixture，避免旧路径造成跳过。

## 运行和维护边界

本仓库不要求容器。容器选择、挂载、EDA setup、许可证环境和 MCP 启动配置由使用者
在各自机器上管理，本次迁移不包含这些配置，也不恢复已删除的 xeda-runner。
仅包含项目源码；不提交 Synopsys 头文件、库、测试数据库或编译产物。

已配置合法可用的 Verdi 开发环境后，从仓库根目录运行 `make xcov` 构建
`xcov/libexec/xcov-npi-worker`；修改 xdebug 后另需 `make xdebug`。
构建依赖 `VERDI_HOME` 下的 NPI 头文件与库。不同系统、架构或 Verdi 安装应重新构建
并验证，不把本机已通过等同于所有环境均支持。

以下 workaround 当前属于本分支行为，需要在后续版本中持续审查：

1. 初始实现曾固定设置 `VCS_USE_MALLOC=1`；维护复审后已撤销共享强制值。
   本次 SPI VDB 加载曾在 `libsnpsmalloc::mem_malloc` 崩溃、系统分配器对照通过，
   因此本机显式选择 `XVERIF_XCOV_NATIVE_USE_MALLOC=1`，其它站点默认继承自身环境。
   该选择只影响 worker；详见 `RUNTIME_MAINTENANCE_REVIEW_2026-09-27.md`。
2. worker 保留参数存储和永久原生句柄。RPC release 注销对象 ID，底层内存随会话
   进程退出统一回收；长会话应关注内存增长。
3. 为避开观察到的关闭阶段原生后台线程崩溃，close/end 回复后使用进程退出回收，
   不调用数据库关闭和全局析构。EL 必须显式保存，关闭不会自动保存。
4. 同一源码行含多个 statement bin 时，CSV selector 仍返回 `TARGET_AMBIGUOUS`；
   不任选一个或扩大排除范围，精确排除状态用原生 EL 保存。

## 验证记录

迁移的 31 个源码、测试和文档文件与此前验收的修复工作树逐字节一致；不迁移本机
AGENTS 复盘、临时诊断脚本、缓存和日志。下面区分原工作树验收与新目录检查。

此前相同源码在 Linux / Verdi V-2023.12-SP2 上完成：

- 最终相关 7 套件共 277 个唯一测试均有通过记录。整组为 276 通过、1 个新增测试
  stub 缺接口而失败；补齐 stub 后该项正式复验通过，并非单轮 277/277。
- modport 相关叶测试 10/10 通过；Fake LSF 3 个场景通过。
- 实际 SPI MCP 查询、波形导出及驱动追踪通过；排除、保存 EL、重开加载、卸载恢复
  完整流程通过。line 计数为 618/635 → 618/634 → 618/634 → 618/635。
- 安装后的 x-npi helper 成功完成唯一 RTL 行的 strict CSV→EL 编译与加载。
- 较早的广覆盖回归为 1529 通过、1 个超时、3 个 SSH 跳过，发生在最终 coverage
  修复之前，不能当作最终版本全仓通过的证据。

新目录的正式 fast focused 检查为 **107 通过**，覆盖 `testinfra.unit`、
`skills.x_npi`、`skills.xverif`、`skills.public_docs`：

```bash
PYTHONPATH="$PWD/xloc:$PWD" .conda-xverif/bin/python -m pytest \
  --xverif-gate fast \
  --xverif-suite testinfra.unit \
  --xverif-suite skills.x_npi \
  --xverif-suite skills.xverif \
  --xverif-suite skills.public_docs
```

新目录的 `make xcov` 构建成功；生成的 worker 由 `.gitignore` 排除，不进入提交。

在配置好的 EDA 环境运行相关 regression 前，先使用 `--xverif-plan` 核对选择，
并按 catalog 显式准备缺失 fixture。原始 7 套件为 `testinfra.unit`、`xcov.unit`、
`xcov.edge_cases`、`xcov.exclusion_npi`、`xcov.urg_backend`、`xcov.modinfo_complex`、
`skills.x_npi`；禁止缺少 fixture 时以跳过替代验证。

许可证初始化曾出现长时间等待，本补丁未解决许可证服务延迟。真实 LSF、免密 SSH、
商业 VIP 和其他 Verdi 安装尚未完成验证。此前验收结果可支持迁移的同一份源码，
不能代替未来代码或环境变化后的回归。
