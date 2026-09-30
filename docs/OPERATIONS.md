# 运维与复验

## 模式与健康

Mock 和真实模式使用不同数据库。入口检测已有比赛的 mock 标记，发现混用即拒绝业务写入。切换环境前先更换数据库连接，不要删除历史数据来“清理模式”。生产 APP_ENV=production 必须配置 PG、随机 JWT 密钥并关闭 Mock。

`/health` 只说明进程响应；`/ready` 必须 PG 和 Redis 都成功才返回 200。Provider 健康独立展示，不因 API 进程正常就认定供应商正常。当前本机演示 PG 正常、Redis 缺失，所以 readiness 为 503 是预期结果。

## 调度

目录同步约 5 分钟；赔率周期按最近未开球比赛计算：大于 24 小时 30 分钟、24→6 小时 10 分钟、6→1 小时 5 分钟、60→15 分钟 1 分钟、最后 15 分钟 30 秒。供应商最小间隔具有更高优先级，所有资源和每次重试共用 Redis 速率门。

每源任务锁 660 秒，执行最多 600 秒；429 设置 Redis 冷却，连接失败不能绕过限流采集。Redis 故障进入可见失败记录。重复手动任务标记 SKIPPED/BUSY，启动时将超过 11 分钟的遗留 RUNNING/QUEUED 标为 INTERRUPTED。不开球后滚球任务。Mock 模式可无 Redis 手动演示，不具有生产跨进程保证。

## 排障与重处理

1. 数据质量页面定位 provider 与失败 request_id；同步任务页面查看状态、错误码、Raw ID。
2. 管理员查看 Raw。解析问题修复后通过 `/api/v1/admin/raw/{id}/reprocess` 提交理由重处理；Raw 不修改，老赔率不覆盖。
3. 映射审核显示候选、分数、主客和时间；确认、拒绝和重绑均需理由及版本。缺少稳定队 ID 时只做逐场确认，不能推断永久身份。
4. 结构化服务日志输出至 stdout，包含 timestamp、level、module、provider、operation、request_id、match_id、duration_ms、status、error_code。管理页面“审计日志”展示数据库变更审计，不是全文服务日志检索器。

## 数据保护与容量

目前不自动清理 Raw/赔率/观察/审计。生产需配置 PG 定期备份和恢复演练；先在独立数据库用 pg_dump / pg_restore 演练并核验行数、约束、触发器、Raw 哈希，不以“备份文件存在”代替可恢复验证。

千万行级尚未压测。先用实际样本与 EXPLAIN ANALYZE 验证窗口查询及当前值访问，再考虑 latest 缓存、按月分区、冷存储。分区前需处理跨分区去重唯一性，不能先删除老数据再优化。保留期应按容量、授权和审计需求制定，当前没有自动删除作业。

容器不向公网暴露 PG/Redis。认证限流已完成下方本机验证；外部上线前仍需落实 TLS、账号恢复、密钥管理、最小权限数据库账号、备份监控和告警，见 BACKLOG。后台在线开关只影响已配置 Adapter，新增密钥/URL 后需要重启服务。

## 本机可复验脚本

从项目根目录运行：

```powershell
.venv/Scripts/python.exe infra/check_local.py
.venv/Scripts/python.exe infra/backup_restore_drill.py --pg-bin .runtime/pgsql/bin
```

预检只读检查 PG、迁移版本、Redis、Docker Engine、API health/ready、今日数据模式与海外凭据配置，不打印密钥。报告写入 artifacts/local-preflight.json。存在阻塞或未经真实验证项时退出码为 1，这是实际失败信号，不应忽略并当作验收通过。

恢复演练使用 DATABASE_URL，通过 pg_export_snapshot 让 pg_dump 与源表哈希处于同一只读快照。恢复目标由脚本随机生成，只有本次成功创建的临时数据库才会被删除；不会恢复到或清空已有数据库。源账号需要创建/删除数据库权限。备份包含用户密码哈希等业务内容，只保存在被 Git 忽略的 artifacts/backups，按敏感备份保管。

脚本比较每表行数与 SHA-256、约束和触发器，重新计算每条 Raw 内容哈希，并在恢复库对六张不可变表各执行一次 UPDATE / DELETE 验证保护，操作全部回滚。PG 可能重写 CHECK 表达式中的数组类型转换；比较前将两边表达式用相同列类型重新解析为一致形式，仍逐项比较定义，不忽略差异。失败报告和备份保留，不覆盖。

当前备份使用 no-owner / no-acl，不包含数据库全局角色和授权恢复；全表 JSON 排序校验适用于本机小数据集，不等同千万行压测、生产 RTO/RPO 或异机灾备。官方机制参考：[pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)、[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)。

## 认证限流

默认固定窗口 900 秒：每个账号最多 10 次登录、每个来源最多 60 次登录、10 次注册、120 次刷新。对应 AUTH_WINDOW_SECONDS、AUTH_LOGIN_ACCOUNT_LIMIT、AUTH_LOGIN_IP_LIMIT、AUTH_REGISTER_IP_LIMIT、AUTH_REFRESH_IP_LIMIT，可在 .env 调整。有效的失败和成功尝试都消耗额度，防止并发绕过；窗口边界可能允许相邻两个窗口的突发量，生产仍需边缘流量保护。

超过额度返回统一 JSON 429 和 Retry-After 秒数，不返回账号是否存在；数据库限流不可用返回 503。短期计数过期后在下一次认证时清理。登录失败没有保存密码或原始邮箱/IP。参考 [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)。

程序仅使用 ASGI 连接来源，不自行信任 X-Forwarded-For。生产反向代理必须由 Uvicorn 的显式可信代理设置决定真实客户端 IP；不要设任意来源可信。未配置可信代理时，同一反向代理后的用户共享来源预算，账号预算仍独立有效。当前环境未做生产代理链压力测试。
