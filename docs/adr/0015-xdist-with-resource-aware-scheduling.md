---
status: accepted
---

# 使用 pytest-xdist 并增加资源感知调度

xverif 引入 pytest-xdist 负责 worker 生命周期、并行执行和结果汇总，自有 pytest plugin 根据 catalog 中的资源声明约束调度。suite 可以声明 CPU、内存、VCS/Verdi/VIP license、独占缓存、端口或其它共享资源；无冲突 suite 并行，共享受限资源通过具名 token/跨 worker lock 控制。

## Considered Options

- 选择：pytest-xdist 加 xverif 资源感知调度层。
- 拒绝：全部串行；实现简单但无法利用不可变数据库 Fixture 的并发读取能力。
- 拒绝：在自有 plugin 中重写多进程 scheduler；会重复 pytest/xdist 已解决的 worker、崩溃和结果汇总问题。

## Consequences

- catalog schema 必须声明 suite 的并行安全性和资源 claim；缺少声明不得默认为无限并行。
- fixture prepare 与 fixture validation 使用独立资源队列和指纹锁，不能与普通只读测试混用写锁。
- 资源 token 的容量来自显式配置；不得在容量不足时静默切换 backend、减少覆盖或改成 fake license。
- plugin 必须验证 worker crash、timeout、Ctrl-C 和 session teardown 时能够释放 token 与锁。
