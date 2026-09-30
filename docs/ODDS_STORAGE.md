# Odds storage

报价（odds_snapshots）与观察（odds_observations）分离，均只追加。相同有效时刻的同价报价去重，
再次采集通过 observation 保存采集时间和对应 Raw。没有供应商有效时间时按采集时刻记录真实观察。
去重键包含比赛、供应商、公司、市场、选项、盘口、赔率、有效时间和映射版本，Decimal 归一后计算。
批量 INSERT ON CONFLICT DO NOTHING，数据库唯一索引处理并发。历史 UPDATE/DELETE 在数据库被拒绝。

latest 使用窗口 row_number 按完整报价序列分组，优先供应商有效时间；晚到的旧报价不会冒充最新报价。
analysis_cutoff 同时约束 collected_at、created_at、published_at、effective_at。
因此后补历史不会出现在之前的系统可见数据中，未知发布/生效时间保持 NULL。

FIRST_OBSERVED 仅代表系统首次看到；PROVIDER_OPEN/CLOSE 只有供应商明确提供时才允许使用。
T_24H/T_6H/T_3H/T_90M/T_30M/T_15M/T_5M/LAST_PREMATCH 只选择目标之前真实观察到的报价，
不得使用目标之后的数据补齐。若错过窗口则留空。更改开球时间会产生新的标签版本（按 kickoff_at 区分）。

前台历史分页，当前赔率不扫描并传输全历史。初始使用复合索引；生产启用 EXPLAIN ANALYZE 验证实际数据。
未来按月分区需要单独去重登记表解决跨分区唯一性。暂不自动删除任何 Raw、赔率或审计历史。
长期存储可迁移冷数据到对象存储，但须保留检索、哈希和恢复演练。

固定标签另存 observed_at，保证去重后仍知道目标前最后观察时间；API 提供 observation_gap_seconds，避免把很久前观察误报为精准时刻采样。标签和查询按映射版本隔离：撤销或重绑后，当前视图隐藏失效绑定，截止时刻查询仍按不可变审计恢复当时的确认状态。

示例（UTC 时间）：`GET /api/v1/matches/{UUID}/odds?market=ASIAN_HANDICAP&analysis_cutoff=2026-09-29T09:30:00Z`，从返回项按 provider/bookmaker 读取当时最新亚洲盘。北京时间昨天 17:30 对应 UTC 09:30；没有当时可见记录时返回空，绝不使用后来采到的数据补答。
