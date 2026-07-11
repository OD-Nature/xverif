# xdebug realdata tests

realdata 测试只通过 manifest 描述真实项目资源，不在 Python 测试代码里硬编码
FSDB、daidir、top 或信号路径。

运行：

```bash
pytest --xverif-gate nightly --xverif-suite xdebug.realdata
```

manifest 放在 `manifests/` 下，每个 case 至少描述：

- `name`
- `fsdb` 或 `daidir`，combined case 同时提供二者
- `top`
- `tags`
- `queries`

每条 query 使用 xdebug JSON action 名和 args，`expect` 使用 invariant，而不是
完整 golden diff。真实数据的目标是验证大层级、大 FSDB/daidir、真实接口和真实
时序窗口不崩溃、不 silent success，并返回关键字段。
