# ADR-005: 不可变 Feature 与未来 Prediction Snapshot

状态：接受。范围：P4-0～P4-2；2026-10-01。

Feature 是独立事实产物；持久化 match_id、analysis_cutoff、feature_version、feature_data、data_quality_score、created_at、mock。数据库唯一键为 (match_id, analysis_cutoff, feature_version)，INSERT ON CONFLICT DO NOTHING 后读回胜出记录，重复或并发请求返回同一 id。新截止时间或新版本追加，绝不覆盖。

feature_data 使用固定七个顶层分组；Decimal 编码为字符串，排序和同时间 UUID 决胜规则固定；不把生成时间或随机数放进特征内容。保留比赛版本、报价、观察、Raw、映射审计及历史赛果/统计 id，能追踪构建依据。缓存以外的 build_feature_data 用于重建验证。

未来 Prediction Snapshot 必须引用具体 feature_snapshot_id 并携带 model_version、feature_version、cutoff、输出和可重现工件信息；本轮只确定这项原则，不创建预测表或模型。模型重跑不能 UPDATE 历史预测，标签与输入必须分开。

代价：保留所有版本占用存储；GET 首次物化一条确定性缓存记录。缺少当时的可见性凭据时必须返回缺失，不能用当前数据补齐。
