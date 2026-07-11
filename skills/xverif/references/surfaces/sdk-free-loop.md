# SDK-free Loop Surface

只有没有 MCP SDK 或必须脚本化/托管 LSF stdio-loop 时使用。该 surface 使用 `method/params` JSONL，当前 loop method 的 session 参数名是 `session`，不能与 MCP tool 的 `session_id` 或原生 envelope 的 `target.session_id` 混用。

协议、readiness、UDS 和 LSF 细节统一转到 `xverif-admin`；普通 action 语义仍回到对应 capability。
