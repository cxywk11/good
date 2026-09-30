# Data ingestion boundary

实现：`jc.ingestion.IngestionService`。保存 Raw 的独立事务与业务解析事务分离。
编排：`jc.jobs.Coordinator.execute` 是将来 Celery task 的调用入口。
Redis 提供跨进程 provider 锁和 account-wide 限流，APScheduler 仅触发协调器。
HTTP 请求、重试和多联赛请求共享限流。生产 Redis 故障时停止外部采集并记录失败，不绕过配额。
