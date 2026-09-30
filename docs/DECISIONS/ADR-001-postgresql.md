# ADR-001: PostgreSQL 主存储

选择 PostgreSQL 17，利用 JSONB、窗口查询、事务、唯一索引与不可变数据触发器。
SQLite 仅为本地开发提供兼容性。PostgreSQL 集成验证单独记录。
暂不分区，保留未来按 collected_at 月分区的迁移路径；分区会影响全局去重唯一键，需先设计去重登记表。
