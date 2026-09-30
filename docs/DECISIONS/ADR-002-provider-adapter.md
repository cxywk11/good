# ADR-002: Provider Adapter

供应商（provider）与博彩公司（bookmaker）独立：聚合供应商可返回多个 bookmaker。
业务只消费统一契约。所有响应先写 Raw，再规范化；不支持的历史 API 显式失败。
博彩公司的展示名称并不意味着具有该公司的真实 API 凭证或覆盖；实际覆盖以返回数据为准。
