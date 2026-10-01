# P4-4D2B Pilot Dataset Report

核验日期：2026-10-01。结论：**BLOCKED — Pilot blocked by target-pool evidence**。
完成了 Source Discovery、Raw-first 探测工具、阻塞报告和离线测试；**未完成真实 Pilot 数据采集/密封/回放**。
当前不适合扩大到三个完整赛季。

## 范围和实际工件

- 候选窗口：2026-09-26～2026-09-28，均为过去日期；实际已验证的体彩销售日为 0。
- 官方查询是 matchBeginDate/matchEndDate，尚不能把该窗口称为已验证的三个销售日。
- 规模目标 50～100 场，本次取得 0 场；没有为了达标补造比赛、球队 ID、时间或赔率。
- 26 次 probe 记录、25 个 HTTP response Raw、1 个缺密钥配置阻塞；Dataset Raw 0。
- 本地汇总：`artifacts/research-probes/20261001-discovery/pilot-report-v2.json`。
- 本地映射：同目录 `entity-mapping.json`，空映射保留阻塞状态；未进行字符串模糊匹配。
- Raw、报告和空映射都在 Git-ignored artifacts，没有把授权数据或原始页面提交 Git。
- 没有创建空 SEALED、假的 VERIFIED、BUILDING 占位版本或虚假 Research Run。

## 按需求逐项汇报

| # | 项目 | 事实 |
|---|---|---|
| 1 | 查找来源 | 体彩官方页面/API/JS；The Odds API；football-data.org；Football-Data.co.uk |
| 2 | ACCEPTED | 0 个真实数据源；公开文档可访问不代表数据已通过准入 |
| 3 | BLOCKED | 体彩历史 API 567；The Odds API 缺密钥、匿名历史请求 401 |
| 4 | 体彩官方历史接口 | `https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry`，参数/原件哈希见 RESEARCH_SOURCES |
| 5 | 官方真实比赛 | 0 场；只得到拦截 HTML，没有比赛 JSON |
| 6 | VERIFIED | 0 场 |
| 7 | 海外历史赔率源 | The Odds API 历史接口在官方文档中确认；本机未取得数据、账户付费权限未验证 |
| 8 | 时间戳 | 只有实际 retrieved_at；published/effective/replay_available/basis 未获得证据，保持 null；Odds 文档的 snapshot timestamp 未用于任何真实记录 |
| 9 | 比赛结果源 | 体彩受阻；football-data.org 对窗口返回空数组；Football-Data.co.uk 仅研究字段说明 |
| 10 | Team ID 源 | 体彩脚本、football-data.org 文档都有 provider ID 字段；未取得真实 ID，映射数 0 |
| 11 | Pilot 日期 | 请求 2026-09-26～28；没有确认任何销售日 |
| 12 | Target 数量 | 0 |
| 13 | VERIFIED Target 数量 | 0 |
| 14 | 外部 1X2 coverage | 0 场 |
| 15 | 亚洲盘 coverage | 0 场 |
| 16 | 大小球 coverage | 0 场 |
| 17 | T-30M coverage | 0 场；run BLOCKED_NOT_RUN |
| 18 | T-90M coverage | 0 场；run BLOCKED_NOT_RUN |
| 19 | T-6H / T-360M coverage | 0 场；run BLOCKED_NOT_RUN |
| 20 | 常规时间赛果 coverage | 0 场 |
| 21 | 两队各 ≥5 历史结果 coverage | 0 场；没有填默认 lambda，也未运行 Goals 估计器 |
| 22 | SEALED Dataset ID/version/hash | 均无；`jc-football-pilot` 仅为预定 key，未创建版本 |
| 23 | Market evaluable | 0 场 |
| 24 | Goals evaluable | 0 场 |
| 25 | common evaluable | 0 场 |
| 26 | Gate A～F | 全部 BLOCKED，原因见下表 |
| 27 | 测试 | 新增测试 20 passed / 1 网络项 skipped；完整回归结果见后文 |
| 28 | 扩展三个完整赛季 | **不适合**。官方池和历史赔率均未打通，时间覆盖、赛果和身份都没有真实样本可验证 |

以上 0 是本次取得或可用的数量，**不是实际开售池大小，也不是 0% 覆盖率**。
分母尚未建立，比例为 N/A（机器报告为 null）。体彩 SPORTTERY_HAD / HHAD / TTG 各 0 场。
Market raw coverage 和 historical timestamp coverage 独立统计；即使只拿到无时刻赔率也不能增加 cutoff coverage。

## Gates 与 cutoff

| Gate | 状态 | 阻塞事实 |
|---|---|---|
| A 官方 Target | BLOCKED | 官方历史接口 HTTP 567，未取得真实开售记录 |
| B 历史赔率时间 | BLOCKED | 缺 The Odds API 密钥，无真实快照；其他价格说明不能替代 |
| C REGULATION FT | BLOCKED | 没有已验证 Target 的常规时间结果或 finished_at 证据 |
| D 稳定实体 | BLOCKED | 没有实际 Target 球队 ID，也没有可核验的跨源映射 |
| E SEALED | BLOCKED | 没有满足 D2A 的真实 ResearchImport；没有调用直接 INSERT 或修改 Seal 条件 |
| F RESEARCH_REPLAY | BLOCKED | 没有 SEALED 的真实数据，按 Gate A 失败策略停止真实回测 |

T-30M、T-90M、T-360M 三项分别保留 BLOCKED_NOT_RUN、run_id=null。
没有声称已成功运行其中任何一个，也没有用合成 fixture 为真实 Gate 加 PASS。
没有模型优胜判断、xG/Elo/ML/Ensemble/推荐/EV/ROI。

## 验证与边界

新增 `tests/test_research_providers.py`、`tests/test_research_pilot.py`。
离线 HTTP 响应与 probe summaries 明确标为 synthetic，只测试安全/控制流，不冒充真实 source fixture。
覆盖失败及非 JSON 的 Raw-first、落盘失败先于解析、D2A secret guard、敏感参数/正文、
异常不泄密、网络开关、无重试/跳转、编码无损、追加保留、日期上限、拒绝假 VERIFIED、
第三方不能打开 Gate A、空分母和三个未运行 cutoff。
网络测试仅在显式 `RESEARCH_NETWORK_ENABLED=1` 时执行，普通 pytest 跳过。

本轮实际验证结果：

| 检查 | 结果 |
|---|---|
| 新增两个测试文件 | 20 passed、1 skipped |
| 全量 pytest（SQLite 默认路径） | **754 passed、1 skipped**，139.06 秒；既有 Starlette/httpx 弃用警告 1 条 |
| Ruff：apps/api/src + tests | 通过 |
| Mypy：apps/api/src | 通过，46 个 source files |
| Alembic heads | `009_research_dataset_persistence`，单一 head |
| 现有 PostgreSQL 的 alembic check | **未通过环境连接检查**：127.0.0.1:55432 连接超时，postgres 进程未运行；未宣称完成 PostgreSQL 复验 |
| 本地 Raw 审计 | 25 个均通过 D2A secret guard 与 canonical hash 重算；未脱敏正文按编码还原后的响应 SHA-256 一致 |
| Git / 冻结边界 | artifacts 确认 ignored；research-replay-v1、D2A contracts/importer/repository、migrations 无 diff |

`research-replay-v1`、D2A import/Seal/Load、LIVE providers、analysis_visibility 与现有迁移均未改变。
Migration head 保持 `009_research_dataset_persistence`。

恢复工作需要先取得官方可访问/授权历史开售证据和合法历史赔率权限，再在相同小窗口验证真实响应，
实现对应 Research Provider、实体 manifest、D2A 导入和三个独立回放。任何 mapping/source/timestamp/Raw 修正
都需要新 dataset version。当前停止在阻塞证据，不自动扩大范围。
