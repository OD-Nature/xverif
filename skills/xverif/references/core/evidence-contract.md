# 证据合同

验证结论尽量保留：

- signal、hierarchy path、scope；
- time、time range、clock edge；
- sampled value 和 known/unknown；
- driver/load、file:line、source context；
- action/tool 和 finding/error code；
- config 名称及来源；
- truncated、partial、missing 和 unknown 状态。

图片用于发现宏观模式，不替代确定性 action 证据。响应为 truncated/partial 时缩小范围或使用 schema 支持的 limits/export，不能当作全量。
