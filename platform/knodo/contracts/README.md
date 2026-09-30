# Knodo 版本化契约副本

这里只保存根目录 `contracts` 的本地语义 schema 发布副本，与三位教师、Designer、记忆助手和 Skill 对齐。教学／教研契约保留 `1.0.0` 版本，记忆使用独立的 `k12.memory.extract.*.v1`。它们不是 Knodo 官方 HTTP 请求／响应定义。

实际 HTTP 适配在 `backend/app/integrations/knodo`；记忆提取入口在 `backend/app/modules/ai/extraction.py`，均包装成官方 Bot Chat 请求。校验器核对协议副本和 SHA，不根据未知字段猜接口。Knodo 官方接口与历史 wire 证据说明见 [Simple API](../../../docs/integrations/knodo/SIMPLE_API_SUMMARY.md)。
