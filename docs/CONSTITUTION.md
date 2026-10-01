# 竞彩智研工程宪章

1. 中国体育彩票实际开售竞彩足球比赛是系统主比赛池唯一入口。
2. 外部供应商存在比赛但中国体彩未开售时，不得进入主比赛池。
3. 外部供应商只能补充赔率、球队、阵容、统计等信息。
4. 原始数据 Raw Data 必须保留，不允许只保留处理后的结果。
5. 所有数据必须记录数据来源。
6. 所有赔率必须记录采集时间。
7. 所有重要状态变化必须可以追溯。
8. 不允许覆盖历史赔率。
9. 不允许通过 UPDATE 修改旧赔率记录来表示新赔率。
10. 不允许将球队名称字符串直接作为跨数据源关联依据。
11. 必须建立统一 Entity ID。
12. 不确定的实体映射不得强行自动匹配。
13. 所有 Provider 必须通过 Adapter 层接入。
14. 业务代码不得直接依赖某一家具体数据供应商。
15. 所有时间统一存储 UTC，同时保留比赛当地时区和北京时间展示能力。
16. 后续预测必须能够严格按照 analysis_cutoff 恢复当时可见数据。
17. 数据缺失允许为空，禁止编造。
18. 所有 Schema 变更使用数据库 Migration。
19. 所有核心模块必须有测试。
20. Phase 0–3 的“禁止预测/AI 推荐”是历史阶段限制，不删除或追溯改变当时的数据设计。
21. Phase 4 允许按明确子阶段增加预测能力；所有未来预测必须 append-only，绑定 analysis_cutoff、model_version、feature_version，可重复、可回测，不允许未来数据泄漏，缺失不得编造。
22. 历史 Feature 只能消费截止时刻已可见的不可变证据。供应商发布时间、生效时间、采集时间不能代替系统可见时间；后补数据和晚提交事务不能反向进入历史输入。
23. Feature、赛果、赛后统计和可见性凭据不得 UPDATE/DELETE；纠错追加事实或升级版本。PostgreSQL 是生产 Schema 基准，SQLite 快测不能代替 PostgreSQL 验证。
24. Goals-only Football Baseline 只能消费冻结 Feature 的目标实体 ID 与历史赛果，不读取赔率或 xG、不查询当前状态；跨源冲突整场排除，样本不足不得使用默认 lambda。规则变化必须升级估计器版本；基线概率不等于最终预测或推荐。
25. Model Evaluation 仅消费冻结不可变样本，使用版本固定的 Decimal 指标、校准桶及排除规则；不得重归一错误概率、静默重复计数、猜测 coverage 分母或输出 winner。跨模型配对必须按共同 match_id 比较，不能用不同样本集的 aggregate 差替代。
26. FROZEN_SAMPLE_SET 只说明评估输入已固定，不构成无泄漏或线上可见证明。LIVE_AS_OBSERVED 与 RESEARCH_REPLAY 必须严格分开；导入旧赛季数据不得生成过去的 live-visible FeatureSnapshot，不得用 provider published_at 或其他推测时间伪造 analysis_visibility。
27. Research Replay 只能消费显式不可变历史 contract，以来源时间证据建立 replay_available_at 和有限 availability_basis；无可靠证据保持不可回放，不猜日期或固定延迟。输出必须声明 RESEARCH_REPLAY、live_visibility_proven=false，不能写入 live FeatureSnapshot/MarketModelSnapshot。
28. 一个研究 run 只能有一个 cutoff policy；目标赛果无条件排除于 Feature（含质量计数与 input provenance），仅作为赛后 Evaluation Label，label_record_ids 独立。目标比分冲突不得投票、选最新或优先来源；历史输入冲突交给已版本化的 Goals 规则。研究规则在验收冻结后变化必须升级 replay_version，provenance 必须保留 dataset/version、cutoff、来源及记录 ID。
29. ResearchDataset 对所有赛果（包括目标 Label）强制 finished_at > kickoff_at，非空 replay_available_at ≥ finished_at；违反则拒绝 Dataset，不静默过滤或修正。Label 可以晚于 cutoff，但不能违反真实事件顺序；published/effective 仅在被选作 availability basis 时自然受终场约束，不一概附加来源时间语义。
30. Research Evaluation Target 必须属于中国体彩实际开售竞彩足球比赛池；P4-4D1.1 至少要求非空 sporttery_match_id，缺失固定 NOT_REPLAYABLE + TARGET_NOT_IN_SPORTTERY_POOL。D2 真实导入必须验证官方体彩历史开售池来源，外部任意字符串不构成证明。研究历史上下文可以包含其他可信比赛，此例外不扩充分析目标池。
31. Evaluation Target 与其每条 Result 的 home_team_id / away_team_id 必须完整且严格一致；缺失则 NOT_EVALUABLE、已知身份矛盾则 Dataset 拒绝，不猜球队或仅按比分生成 HOME/DRAW/AWAY。Match 的 (source, source_record_id) 必须唯一；input_match_ids 只存 canonical research_match_id，input_record_ids.match_source_records 只存真正 source_record_id，并保留 source 关联证据。

历史 Phase 0–3 禁止预测、P_model / P_final、BUY / WATCH / PASS、投注金额、串关、实时比分、滚球、自动投注，该约束保留为历史范围记录。
当前已授权 P4-0～P4-3 文档、赛后事实、Feature 基础设施和仅消费冻结 Feature 的市场定价基准，以及 P4-4A 显式参数的纯比分概率数学层、P4-4B1 冻结赛果的 Goals Baseline Lambda Estimator；Market Snapshot 同样数据库级 append-only。P4-4B1 每队最近 20 场、至少 5 场、等权计算 GF/GA 与 lambda，rho 固定 0；不增加模型持久化或预测 API。P4-4C 增加纯 Model Evaluation Core，只做冻结样本的 Log Loss、Brier、Accuracy、Calibration/ECE、coverage、配对比较与时间划分契约，不进行真实历史研究或模型训练。P4-4D1/D1.1 已人工复核并冻结 research-replay-v1；P4-4D2A 授权独立 Research 持久化与本地 fixture 导入，不接入真实历史网站。禁止 CORE/WATCH/PASS、EV 推荐、串关、LLM 推荐、自动投注和最终预测模型；历史采集、xG、Elo、rho 拟合、Model Snapshot、Ensemble 等后续能力等待复核和另行授权。赛后 FINAL 事实不属于实时比分或滚球服务。
演示样例必须包含 mock=true，生产环境不允许启用演示。

P4-4D1.1 是 pre-acceptance correctness fix，保留 research-replay-v1；现已通过人工验收，v1 正式冻结，之后任何研究规则变化必须升级 v2。D2A 仅增加独立持久化，不改变冻结规则，仍不能形成真实历史三赛季结论。

32. Research 仅存 research_* 表，不读写 LIVE matches、versions、odds、results、stats、Feature/Market snapshots 或 analysis_visibility；内部持久化采用独立 Core 事务，不触发 LIVE ORM 可见性扫描。
33. Research Dataset 以 (dataset_key, dataset_version) 唯一命名，BUILDING 只能转 SEALED 或 REJECTED；成员始终 append-only，终态不再追加。数据库必须强制保护，封存失败保留 BUILDING，不跳过坏行。
34. 每条 Research normalized 记录必须有同 dataset/source Raw 工件。Raw 按 canonical payload SHA-256 幂等，修正追加新工件；Dataset 另算稳定业务内容 hash，不含存储 UUID/创建时钟，封存后修改内容必须新版本。
35. 来源验证必须显式声明且有时间/说明，synthetic source 固定 UNVERIFIED。真实体彩目标必须 VERIFIED 并关联经核验的官方历史开售 Raw 与对应球队/开球身份；测试 fixture 不构成实际开售或模型质量证明。
36. Research Import/Seal/Load 复用冻结 v1 的 availability 与 chronology，缺证据保持 NULL，不推断可用时间。只物化 SEALED ResearchDataset，再交给原纯 replay；源 metadata 不得存 API key、Authorization、cookie、password 或 token。

D2A 只授权 Schema、显式 Import Contract、Raw Artifact、Dataset Version、Validation、Append-only、Materialization；禁止互联网爬虫、公开研究上传/回测 API，以及自动进入 D2B。当前没有真实三完整赛季 + 当前赛季数据。完整决定见 [ADR-014](DECISIONS/ADR-014-research-dataset-persistence.md)。

2026-10-01 后续授权：D2A 已通过人工复核；P4-4D2B 仅允许 Source Discovery 与 1～3 个历史销售日 / 50～100 场真实 Pilot。
上文 D2A 的禁止联网属于该阶段历史范围。D2B 必须先验证来源、保存脱敏 Raw，再实现独立 Research Adapter；
官方开售池证据失败则 Pilot BLOCKED 并停止真实回测，不绕过验证、不补造 VERIFIED，也不扩展三个完整赛季。
本轮 Gate A～F 全部 BLOCKED，详见 [Pilot 报告](PILOT_DATASET_REPORT.md)；冻结 replay-v1 与所有模型规则仍保持原样。
