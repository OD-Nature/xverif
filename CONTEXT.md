# xverif

xverif 面向芯片验证数据库的查询、分析与调试工作；本词汇表统一描述其测试体系中容易与仿真验证混淆的项目特有概念。

## Language

**数据库 Fixture**:
供 xverif 测试重复消费的 daidir、FSDB、VDB 及其配套元数据；它是可验证来源和版本的测试输入资产，生成它的编译或仿真过程不是 xverif 的测试结论。
_Avoid_: 仿真测试、临时仿真输出

**Fixture 指纹**:
决定数据库 Fixture 是否仍与其生成输入和生成合同一致的内容标识；输入源码、生成脚本、关键工具选项或 fixture schema 改变时，原资产即失效。
_Avoid_: 文件存在标记、mtime 缓存

**Fixture 准备**:
显式构建或获取有效数据库 Fixture 的资产生命周期阶段；它产出测试输入，不产生 xverif 功能是否正确的测试判定。
_Avoid_: 自动测试、隐式仿真

**测试执行**:
使用已验证数据库 Fixture 对 xverif 行为作出通过或失败判定的阶段；它不负责隐式生成缺失资产。
_Avoid_: Fixture 生成、自动 prepare

**Fixture 缓存**:
保存可复用数据库 Fixture 的项目本地资产区；它不属于源码，也不在不同工作区之间隐式共享。
_Avoid_: 用户级共享缓存、fixture 的分散 `out/` 目录
