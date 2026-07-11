---
status: accepted
---

# 以内容指纹复用 daidir 和 FSDB 数据库 Fixture

xverif 的 daidir、FSDB 等可生成数据库被视为测试输入资产，而不是每轮测试都必须重新仿真的临时输出。fixture builder 根据 RTL/TB/filelist、生成脚本、关键 VCS/FSDB 选项、fixture schema 和影响数据库语义的工具版本生成内容指纹；指纹及完整性检查匹配时直接复用，只有 cache miss、指纹失效或显式要求重建时才运行编译和仿真。

## Considered Options

- 选择：内容指纹缓存，并提供显式 `--rebuild-fixtures`。
- 拒绝：人工递增 fixture 版本；容易漏升版本并复用陈旧数据库。
- 拒绝：只检查 FSDB/daidir 路径存在；无法发现生成输入变化，可能产生假通过。

## Consequences

- fixture 必须携带机器可读 manifest、生成指纹和完整性条件，不能只判断文件或目录存在。
- 正常 xverif 测试优先消费有效缓存；仿真是 fixture 准备路径，不是测试本体。
- 真实项目数据库等不可由仓库生成的资产仍可使用外部来源，但必须声明来源身份、所需资源和可验证的版本信息。
- 缓存位置与 cache miss 行为已由 ADR-0005、ADR-0006 和 ADR-0007 明确为仓库本地缓存、准备/执行分离和独立清理语义。
