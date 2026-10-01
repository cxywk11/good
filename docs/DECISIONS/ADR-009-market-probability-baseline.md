# ADR-009: 冻结 Feature 上的市场定价基准

状态：接受。范围：P4-3；2026-10-01。

Market Engine 只消费已保存的 FeatureSnapshot，不查询 OddsSnapshot、Match、MatchVersion、Provider 状态或外部 API。Feature 是不可变输入，Market 是独立派生产物，不回写 feature_data。相同 feature_snapshot_id + market_model_version 返回相同快照，唯一约束和 INSERT ON CONFLICT DO NOTHING 处理并发；数据库触发器禁止 UPDATE/DELETE。

V1 固定 `market-v1` / `proportional-v1`。核心使用 Decimal，局部独立 Context 精度 50、ROUND_HALF_EVEN；输出小数保留 24 位字符串。算法内部概率和容差 1e-45，序列化分布验收容差 1e-23。任何算法、阈值、精度、缺失策略或来源规则实质变更必须升级版本，不重定义旧行。

每个完整市场独立计算 `q_i = 1 / odds_i`、`overround = Σq_i`、`vig = Σq_i - 1`、`p_i = q_i / Σq_i`。仅实现 proportional；MarginRemovalMethod 是一个小 Protocol，未来方法随新版本加入。负 vig 保留并标注 NEGATIVE_OVERROUND；overround > 1.20 标注 HIGH_OVERROUND。阈值只是公开诊断规则，没有历史有效性声明，不调整概率或权重。

完整性要求每个 provider/bookmaker/market/canonical line 独立具备且仅具备全部预期选项，每项恰好一条。缺失、重复、额外选项、混合映射绑定、非法赔率或非法 line 都不能去水。原始赔率及能计算的 raw implied 留存，overround/vig/no-vig 为空；禁止跨公司补项。

外部共识仅使用 provider != sporttery 的完整 1X2，每个 `(provider, bookmaker)` 等权，先逐源去水再取 arithmetic mean。mean 即 P_market；同时保存 median/min/max/population_stddev 和实际来源列表。没有外部完整来源时 source_count=0、统计及 P_market=NULL。体彩无论市场标签为何都不进入外部共识。

不按 bookmaker 字符串跨 Provider 去重，因为尚未建立正式 Bookmaker Entity Resolution；这会带来同一真实公司重复覆盖的风险，必须对使用者公开。V1 不预设“sharp”公司和经验权重。

亚洲盘 HOME 的 canonical_home_line=line，AWAY 的 canonical_home_line=-line。只有互为相反数的 HOME/AWAY 形成完整二项市场；不能配对时保留分组及 HANDICAP_LINE_MISMATCH（有另一方向但在不同 canonical line）和缺项诊断。TOTALS 只在相同 line 下配对 OVER/UNDER。体彩 HHAD 则 HOME/DRAW/AWAY 使用同一个原始让球 line，不翻转 AWAY。

亚洲二项盘与体彩 HHAD 三项不是同一概率空间，TOTALS 与体彩 TTG 的 0～6/7+ 八项也不是同一概率空间。各自保留，不相互转换或补齐。含走盘/半赢半输的二项盘口输出解释为归一化价格，不能声称已推导真实无条件结算概率。

体彩 HAD、HHAD、TTG 可独立去水。`sporttery_external_gap = external_consensus.mean - sporttery_HAD.no_vig`，不是 Edge。无完整外部共识或没有唯一完整 HAD 来源时 gap=NULL；多个完整 HAD 来源标注歧义，不随意选一家或平均。比分盘及半全场标记 unsupported_for_v1，保留原始值。

赔率变化只用 Feature 的 odds_movement.items：delta=current-previous，pct_delta=delta/previous×100，raw_probability_delta=1/current-1/previous；无 previous 时三项 NULL。不同 selection 的 previous 不代表同刻，不输出 previous_market_probability 或去水历史变化。

P4-3 只回答市场如何定价；没有预测、P_final、推荐、Edge/EV、投注或 LLM。受保护的 cutoff/analysis_visibility 原样保留；全历史可见性扫描性能债务留在 BACKLOG，不借本阶段重写底座。下一阶段必须单独授权。
